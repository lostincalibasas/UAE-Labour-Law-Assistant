import streamlit as st
from generate_answer import generate_answer
from evidence_citations import FALLBACK
from rag_errors import RAGError, operational_failure

import os
os.environ["STREAMLIT_WATCHER_TYPE"] = "poll"
st.set_page_config(page_title="UAE Labor Law Compliance Assistant", page_icon="⚖️")

st.title("UAE Labor Law Compliance Assistant")
st.caption("A RAG system grounded in public UAE labor law documents. Built as a portfolio recreation of a production compliance RAG system.")

def display_result(result):
    if result.get("status") == "operational_error":
        # Use our message catalog even if a caller supplies an unsafe message.
        code = (result.get("error") or {}).get("code", "internal_error")
        st.error(RAGError(code, "ui").message)
        return
    verified = result.get("citation_validation", {}).get("status") == "valid" and result.get("citations")
    if verified and result.get("status", "ok") == "ok":
        st.markdown("### Answer")
        st.write(result["answer"])
        st.markdown("### Referenced evidence")
        st.caption("References are verified against the retrieved passages. Whether each passage supports the claim has not been automatically checked.")
        for citation in result["citations"]:
            label = f"[{citation['evidence_id']}] {citation['source_document']}"
            if citation.get("article"):
                label += f" — {citation['article']}"
            with st.expander(label):
                st.text(citation["excerpt"])
                if citation.get("filename"):
                    st.caption(citation["filename"])
    else:
        st.info(FALLBACK)
        st.caption("No verified evidence citations available.")


query = st.text_input("Ask a question about UAE labor law:")

if st.button("Ask"):
    if not query.strip():
        st.info("Enter a question to continue.")
    else:
        try:
            with st.spinner("Searching documents and generating answer..."):
                try:
                    result = generate_answer(query)
                except Exception:
                    result = operational_failure(RAGError("internal_error", "ui"))
            display_result(result)
        except Exception:
            display_result(operational_failure(RAGError("internal_error", "ui")))
