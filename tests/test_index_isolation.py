"""No live Chroma clients or source-index writes; locks use temporary fixtures."""

import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import index_isolation
from index_isolation import locked_snapshot, tree_hashes, install_chroma_guard
from index_paths import PROTECTED_INDEX, resolve_index_path
from index_integrity import collection_fingerprint, logical_differences
from rag_errors import RAGError
import retrieve_bge
import verify_index


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'chroma.sqlite3').write_bytes(b'sqlite fixture')
        (self.source / 'segment').mkdir()
        (self.source / 'segment' / 'vectors.bin').write_bytes(b'vectors fixture')
        (self.source / 'empty').mkdir()

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock test')
    def test_complete_snapshot_preserves_original_and_is_not_hardlinked(self):
        before = tree_hashes(self.source)
        with locked_snapshot(self.source) as snapshot:
            for name in ('reference', 'working'):
                target = self.root / name
                snapshot.copy_to(target)
                self.assertEqual(tree_hashes(target), before)
                self.assertTrue((target / 'empty').is_dir())
                self.assertFalse(os.path.samefile(self.source / 'chroma.sqlite3', target / 'chroma.sqlite3'))
            (self.root / 'working' / 'segment' / 'vectors.bin').write_bytes(b'copy changed')
            self.assertEqual(snapshot.hashes(), before)
        self.assertEqual(tree_hashes(self.source), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock test')
    def test_active_sqlite_or_vector_writer_prevents_snapshot(self):
        for path in (self.source / 'chroma.sqlite3', self.source / 'segment' / 'vectors.bin'):
            with self.subTest(path=path), path.open('r+b'):
                with self.assertRaisesRegex(RuntimeError, 'quiescent snapshot'):
                    with locked_snapshot(self.source):
                        self.fail('Writer must prevent snapshot acquisition')

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock test')
    def test_locks_deny_new_writes_and_deletes(self):
        before = tree_hashes(self.source)
        with locked_snapshot(self.source):
            for path in (self.source / 'chroma.sqlite3', self.source / 'segment' / 'vectors.bin'):
                with self.assertRaises(OSError):
                    path.write_bytes(b'not permitted')
                with self.assertRaises(OSError):
                    path.unlink()
        self.assertEqual(tree_hashes(self.source), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock test')
    def test_added_file_causes_inventory_check_to_fail(self):
        with locked_snapshot(self.source) as snapshot:
            (self.source / 'new-file').write_bytes(b'new')
            with self.assertRaisesRegex(RuntimeError, 'inventory changed'):
                snapshot.hashes()

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing lock test')
    def test_overlapping_or_existing_copy_destinations_are_refused(self):
        with locked_snapshot(self.source) as snapshot:
            for target in (self.source, self.source / 'nested', self.root):
                with self.assertRaises(ValueError):
                    snapshot.copy_to(target)
            target = self.root / 'existing'
            target.mkdir()
            with self.assertRaises(FileExistsError):
                snapshot.copy_to(target)

    def test_unsupported_locking_platform_fails_closed(self):
        with patch.object(index_isolation.os, 'name', 'posix'):
            with self.assertRaisesRegex(RuntimeError, 'Windows'):
                with locked_snapshot(self.source):
                    self.fail('Must refuse unsupported platform')

    def test_paths_resolve_at_call_time_and_guard_original_aliases(self):
        with patch.dict(os.environ, {'RAG_TEST_INDEX_ROOT': str(self.root), 'RAG_INDEX_PATH': str(self.root / 'working')}):
            self.assertEqual(resolve_index_path(), self.root / 'working')
            os.environ['RAG_INDEX_PATH'] = str(self.root / 'reference')
            self.assertEqual(resolve_index_path(), self.root / 'reference')
            for bad in (PROTECTED_INDEX, PROTECTED_INDEX / '..' / 'chroma_db', self.root / 'other'):
                os.environ['RAG_INDEX_PATH'] = str(bad)
                with self.assertRaises(RAGError):
                    resolve_index_path()
            del os.environ['RAG_INDEX_PATH']
            with self.assertRaises(RAGError):
                resolve_index_path()

    def test_cached_original_client_is_never_closed_or_reused(self):
        client = Mock()
        with patch.dict(os.environ, {'RAG_TEST_INDEX_ROOT': str(self.root), 'RAG_INDEX_PATH': str(self.root / 'working')}), \
             patch.object(retrieve_bge, 'client', client), \
             patch.object(retrieve_bge, 'client_path', PROTECTED_INDEX):
            with self.assertRaises(RAGError) as error:
                retrieve_bge.get_collection()
        self.assertEqual(error.exception.code, 'index_isolation')
        client.close.assert_not_called()
        client.get_collection.assert_not_called()

    def test_legacy_retrievers_honor_isolated_path_before_initialization(self):
        for filename in ('retrieve.py', 'retrieve - MINILM.py'):
            factory = Mock()
            with patch.dict(os.environ, {'RAG_TEST_INDEX_ROOT': str(self.root), 'RAG_INDEX_PATH': str(self.root / 'working')}), \
                 patch.dict(sys.modules, {'chromadb': NS(PersistentClient=factory),
                                        'sentence_transformers': NS(SentenceTransformer=Mock())}):
                runpy.run_path(str(PROTECTED_INDEX.parents[1] / filename), run_name='_test_legacy')
            factory.assert_called_once_with(path=str(self.root / 'working'))
            factory.return_value.get_or_create_collection.assert_not_called()

    def test_storage_initializer_guard_catches_hardcoded_paths(self):
        class Shared:
            _identifier_to_system = {}
            calls = []

            @classmethod
            def _create_system_if_not_exists(cls, identifier, settings):
                cls.calls.append(identifier)

        module = NS(SharedSystemClient=Shared)
        allowed = self.root / 'working'
        with patch.dict(sys.modules, {'chromadb.api.shared_system_client': module}):
            opened = install_chroma_guard(allowed)
            for path in (PROTECTED_INDEX, self.root / 'other'):
                with self.assertRaises(RuntimeError):
                    Shared._create_system_if_not_exists(str(path), NS(is_persistent=True, persist_directory=str(path)))
            self.assertEqual(Shared.calls, [])
            Shared._create_system_if_not_exists(str(allowed), NS(is_persistent=True, persist_directory=str(allowed)))
            self.assertEqual(opened, [str(allowed)])

    def test_worker_rejects_original_before_any_chroma_import(self):
        with patch.object(verify_index, 'install_chroma_guard') as guard:
            with self.assertRaises(ValueError):
                verify_index.worker(PROTECTED_INDEX, 'working')
        guard.assert_not_called()

    def test_existing_output_refused_before_snapshot(self):
        output = self.root / 'report.json'
        output.write_bytes(b'preserved')
        with patch.object(verify_index, 'locked_snapshot') as lock:
            with self.assertRaises(FileExistsError):
                verify_index.verify(self.source, output)
        lock.assert_not_called()
        self.assertEqual(output.read_bytes(), b'preserved')

    def test_temp_storage_inside_original_is_refused_before_creation(self):
        with patch.object(verify_index.tempfile, 'gettempdir', return_value=str(PROTECTED_INDEX)), \
             patch.object(verify_index.tempfile, 'mkdtemp') as create:
            with self.assertRaises(ValueError):
                verify_index.verify(self.source)
        create.assert_not_called()

    def test_final_integrity_exception_cannot_report_success(self):
        temporary_base = self.root / 'scratch'
        workspace = temporary_base / 'run'
        workspace.mkdir(parents=True)
        worker_report = {'before': {}, 'differences_after_reopen': {},
                         'retrieval': {'status': 'ok'}, 'opened_paths': []}
        for kind in ('reference', 'working'):
            (workspace / f'{kind}-logical.json').write_text(json.dumps(worker_report))
        with patch.object(verify_index.tempfile, 'gettempdir', return_value=str(temporary_base)), \
             patch.object(verify_index.tempfile, 'mkdtemp', return_value=str(workspace)), \
             patch.object(verify_index, 'locked_snapshot') as lock, \
             patch.object(verify_index.subprocess, 'run', return_value=NS(returncode=0)), \
             contextlib.redirect_stdout(io.StringIO()):
            snapshot = lock.return_value.__enter__.return_value
            snapshot.directories = []
            snapshot.hashes.side_effect = [{'chroma.sqlite3': 'hash'}, RuntimeError('inventory changed')]
            result = verify_index.verify(self.source)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('inventory changed', result['blocker'])


class LogicalIntegrityTests(unittest.TestCase):
    def fingerprint(self, ids=None, documents=None, metadatas=None, embeddings=None):
        collection = Mock()
        collection.metadata = {'hnsw:space': 'cosine'}
        collection.count.return_value = 2
        collection.get.return_value = {
            'ids': ids or ['2', '1'], 'documents': documents or ['second', 'first'],
            'metadatas': metadatas or [{'law': 'B'}, {'law': 'A'}],
            'embeddings': embeddings or [[0.25, 0.5], [0.75, 1.0]],
        }
        return collection_fingerprint(collection)

    def test_order_does_not_change_logical_fingerprint(self):
        a = self.fingerprint()
        b = self.fingerprint(['1', '2'], ['first', 'second'], [{'law': 'A'}, {'law': 'B'}], [[0.75, 1.0], [0.25, 0.5]])
        self.assertEqual(a, b)
        self.assertEqual(logical_differences({'bge': a}, {'bge': b}), {})

    def test_each_logical_component_detects_changes(self):
        baseline = self.fingerprint()
        for changes, expected in (
            ({'ids': ['3', '1']}, 'ids_sha256'),
            ({'documents': ['changed', 'first']}, 'documents_sha256'),
            ({'metadatas': [{'law': 'changed'}, {'law': 'A'}]}, 'metadatas_sha256'),
            ({'embeddings': [[0.25 + 1e-12, 0.5], [0.75, 1.0]]}, 'embeddings_sha256'),
            ({'embeddings': [[0.25], [0.75]]}, 'dimensions'),
        ):
            with self.subTest(expected=expected):
                differences = logical_differences({'bge': baseline}, {'bge': self.fingerprint(**changes)})
                self.assertIn(expected, differences['bge']['fields'])
        self.assertIn('bge', logical_differences({'bge': baseline}, {}))

    def test_duplicate_ids_and_nonfinite_embeddings_are_rejected(self):
        with self.assertRaises(ValueError):
            self.fingerprint(ids=['1', '1'])
        with self.assertRaises(ValueError):
            self.fingerprint(embeddings=[[float('nan'), 0.5], [0.75, 1.0]])


if __name__ == '__main__':
    unittest.main()
