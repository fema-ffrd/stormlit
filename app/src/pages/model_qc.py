# module imports
from ..components.layout import render_footer
from ..configs.settings import LOG_LEVEL
from ..utils.session import init_session_state

# standard imports
import os
import streamlit as st
from dotenv import load_dotenv
import warnings
from rasqc import check

# Suppress warnings
warnings.filterwarnings("ignore")

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv()


def process_qc_results(qc_results, error_col, success_col):
    """
    Process the QC results.

    Parameters
    ----------
    qc_results : list[RasqcResult]
        The QC results to process.
    error_col : streamlit.column
        The container to display error results.
    success_col : streamlit.column
        The container to display success results.
    """
    for item in qc_results:
        if item.result.value == "error":
            tile = error_col.container()
            tile.markdown(
                f"""
                <div style="background-color: #B53737; padding: 10px; border-radius: 5px; border: 1px solid black;">
                    <h4 style="color: white;">Name: {item.name}</h4>
                    <p style="color: white;">Filename: {item.filename}</p>
                    <p style="color: white;">Message: {item.message}</p>
                    <p style="color: white;">Pattern: {item.pattern}</p>
                    <p style="color: white;">Examples: {item.examples}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            tile = success_col.container()
            tile.markdown(
                f"""
                <div style="background-color: #2e6930; padding: 10px; border-radius: 5px; border: 1px solid black;">
                    <h4 style="color: white;">Name: {item.name}</h4>
                    <p style="color: white;">Filename: {item.filename}</p>
                    <p style="color: white;">Message: {item.message}</p>
                    <p style="color: white;">Pattern: {item.pattern}</p>
                    <p style="color: white;">Examples: {item.examples}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def model_qc():
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Model QC")
    st.write(
        """
        This app allows you to perform automated QA/QC checks on HEC-RAS models.
        Each QC result is categorized as either an error or a success according the 
        selected QC check suite. The file name, message, pattern, and examples are 
        provided for each result."""
    )

    st.session_state.log_level = LOG_LEVEL

    st.sidebar.markdown("## Toolbar")

    st.session_state["model_qc_file_path"] = st.sidebar.text_input(
        "Enter the s3 path to the HEC-RAS model file .prj",
        placeholder="s3://pilot-name/models-folder/model-name/model.prj",
        value=None,
    )

    if st.session_state["model_qc_file_path"] is not None:
        # check if it is a valid file path
        if not st.session_state["model_qc_file_path"].endswith(".prj"):
            st.sidebar.error(
                "Please enter a valid HEC-RAS model file path ending with .prj"
            )
            st.session_state["model_qc_file_path"] = None

    st.session_state["model_qc_suite"] = st.sidebar.selectbox(
        "Select a QC check suite",
        ("ffrd"),
        index=0,
    )

    if st.session_state["model_qc_file_path"] is not None:
        if st.sidebar.button("Run QC Checks"):
            with st.spinner("Running QC checks..."):
                # Run the QC checks
                st.session_state["model_qc_results"] = check(
                    ras_model=st.session_state["model_qc_file_path"],
                    check_suite=st.session_state["model_qc_suite"],
                )
                st.success("QC checks completed successfully!")
                st.session_state["model_qc_status"] = True

    col1, col2 = st.columns(2)
    col1.subheader("Errors ❌")
    col2.subheader("Successes ✅")

    if (
        st.session_state["model_qc_status"]
        and st.session_state["model_qc_results"] is not None
    ):
        process_qc_results(st.session_state["model_qc_results"], col1, col2)
    else:
        st.write("No QC results available.")

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)

    # Footer
    render_footer()
