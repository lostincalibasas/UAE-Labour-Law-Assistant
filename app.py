import streamlit as st
from generate_answer import generate_answer

import os
os.environ["STREAMLIT_WATCHER_TYPE"] = "poll"
st.set_page_config(page_title="UAE Labor Law Compliance Assistant", page_icon="⚖️")

st.title("UAE Labor Law Compliance Assistant")
st.caption("A RAG system grounded in public UAE labor law documents. Built as a portfolio recreation of a production compliance RAG system.")

query = st.text_input("Ask a question about UAE labor law:")

if st.button("Ask") and query:
    with st.spinner("Searching documents and generating answer..."):
        result = generate_answer(query)

    st.markdown("### Answer")
    st.write(result["answer"])

    if result["sources"]:
        st.markdown("### Sources")
        for source in result["sources"]:
            st.write(f"- {source}")
    else:
        st.caption("No sources cited.")