import streamlit as st
from agent import agent_answer

st.set_page_config(
    page_title="Assistant Maintenance IA",
    page_icon="🛠️"
)

st.title("Assistant Maintenance IA")
st.caption("Agent hybride SQL + RAG pour l'aide à la maintenance industrielle")

question = st.text_input(
    "Posez une question sur les incidents ou les procédures de maintenance :"
)

if st.button("Analyser") and question:

    result = agent_answer(question)

    if "error" in result:
        st.error(result["error"])

    else:
        st.subheader("Réponse")
        st.write(result["response"])

        with st.expander("Voir la traçabilité"):
            st.write("Outil utilisé :", result["tool"])
            st.write("Arguments :", result["arguments"])
            
            if result["tool"] == "answer_with_rag":
                st.write("Type de source : documentation technique")
                
                if isinstance(result["tool_result"], dict):
                    st.write(
                        "Sources :",
                        result["too_result"].get("sources", [])
                    )
                    
            else:
                st.write("Type de source : base PostgreSQL Neon")
            
            st.write("Résultat brut :", result["tool_result"])