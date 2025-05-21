# module imports
from components.layout import render_footer
from configs.settings import LOG_LEVEL
from utils.session import init_session_state

# standard imports
import os
import pandas as pd
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


def create_tile(st_obj, qc_item, color):
    """
    Create a tile for displaying QC results.

    Parameters
    ----------
    st_obj : streamlit.object
        The Streamlit object to use for displaying the tile.
    qc_item : RasqcResult
        The QC item to display.
    color : str
        The background color of the tile as a hex code.
        The color should be a valid CSS color value (e.g., "#B53737" for red).

    Returns
    -------
    tile : streamlit.container
        The tile container.
    """
    tile = st_obj.container()
    tile_text = f"""
    <div style="background-color: {color}; padding: 10px; border-radius: 5px; border: 1px solid black;">
        <h4 style="color: white;">Name: {qc_item.name}</h4>
        <p style="color: white;">Filename: {qc_item.filename}</p>
    """
    if qc_item.message is not None:
        tile_text += f'<p style="color: white;">Message: {qc_item.message}</p>'
    if qc_item.pattern is not None:
        tile_text += f'<p style="color: white; font-family: monospace;">Pattern: {qc_item.pattern}</p>'
    if qc_item.examples is not None:
        tile_text += f'<p style="color: white;">Examples: {qc_item.examples}</p>'
    if qc_item.element is not None:
        tile_text += f'<p style="color: white;">Elements: {qc_item.element}</p>'
    tile_text += "</div>"
    tile.markdown(tile_text, unsafe_allow_html=True)
    return tile


def process_qc_results(
    qc_results,
    errors_exp,
    warnings_exp,
    successes_exp,
):
    """
    Process the QC results.

    Parameters
    ----------
    qc_results : list[RasqcResult]
        The QC results to process.
    errors_exp : streamlit.expander
        The expander to display QC error details per result.
    warnings_exp : streamlit.expander
        The expander to display QC error details per result.
    successes_exp : streamlit.expander
        The expander to display QC error details per result.

    Returns
    -------
    df : pandas.DataFrame
        A DataFrame containing the summary of QC results.
    """
    count_errors = 0
    count_warnings = 0
    count_successes = 0
    all = 0
    for item in qc_results:
        all += 1
        if item.result.value == "error":
            count_errors += 1
            create_tile(errors_exp, item, color="#B53737")
        elif item.result.value == "ok":
            count_successes += 1
            create_tile(successes_exp, item, color="#2e6930")
        elif item.result.value == "warning":
            count_warnings += 1
            create_tile(warnings_exp, item, color="#EFBF04")
        else:
            st.error(f"Unknown result type: {item.result.value}")
            continue

    if count_errors == 0:
        errors_exp.write("No errors found.")
    if count_warnings == 0:
        warnings_exp.write("No warnings found.")
    if count_successes == 0:
        successes_exp.write("No successes found.")

    df = pd.DataFrame(
        {
            "QC Check": ["Errors", "Warnings", "Successes"],
            "Count": [count_errors, count_warnings, count_successes],
        }
    )
    return df


def model_qc():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Model QC")
    st.write(
        """
        This app allows you to perform automated QA/QC checks on HEC-RAS models.
        Each QC result is categorized as either an error, warning or a success according the 
        selected QC check suite. The file name, message, pattern, and examples are 
        provided for each result."""
    )

    st.session_state.log_level = LOG_LEVEL

    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC 📋")
    st.sidebar.page_link("pages/single_event.py", label="Single Event Viewer ⛈️")

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
    col1.subheader("Results")
    col2.subheader("Summary")
    errors_bin = col1.expander("Errors", icon="❌")
    warnings_bin = col1.expander("Warnings", icon="⚠️")
    success_bin = col1.expander(label="Successes", icon="✅")

    if (
        st.session_state["model_qc_status"]
        and st.session_state["model_qc_results"] is not None
    ):
        summary_df = process_qc_results(
            st.session_state["model_qc_results"], errors_bin, warnings_bin, success_bin
        )
        col2.dataframe(summary_df)
    else:
        st.write("No QC results available.")

    # Session state
    with st.expander("Session State"):
        st.write(st.session_state)

    # Footer
    render_footer()


if __name__ == "__main__":
    model_qc()
