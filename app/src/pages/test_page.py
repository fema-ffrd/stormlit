# module imports
from utils.session import init_session_state
from utils.r_server import get_flow_plot

# standard imports
import os
import json
import traceback
from dotenv import load_dotenv
import logging

# third party imports
import streamlit as st
import plotly.graph_objects as go

currDir = os.path.dirname(os.path.realpath(__file__))  # located within pages folder
srcDir = os.path.abspath(os.path.join(currDir, ".."))  # go up one level to src
assetsDir = os.path.abspath(os.path.join(srcDir, "assets"))  # go up one level to src
load_dotenv('/workspace/app/.env')

logger = logging.getLogger(__name__)


def unwrap_r_plotly(obj, key=None):
    """
    Recursively unwrap R plotly objects that wrap values in single-element arrays.
    
    Args:
        obj: The object to unwrap (dict, list, or primitive)
        key: The current key being processed (to determine context)
        
    Returns:
        The unwrapped object
    """
    # Fields that should remain as arrays even if single element
    array_fields = {'x', 'y', 'z', 'text', 'hovertext', 'ids', 'customdata'}
    
    if isinstance(obj, dict):
        return {k: unwrap_r_plotly(v, k) for k, v in obj.items()}
    elif isinstance(obj, list):
        # Don't unwrap if this is a data coordinate field
        if key in array_fields:
            # But still unwrap nested single-element arrays within the data
            result = []
            for item in obj:
                if isinstance(item, list) and len(item) == 1 and not isinstance(item[0], (dict, list)):
                    result.append(item[0])
                else:
                    result.append(unwrap_r_plotly(item, key))
            return result
        # If it's a single-element list containing a primitive, unwrap it
        elif len(obj) == 1 and not isinstance(obj[0], (dict, list)):
            return obj[0]
        # Otherwise, recursively unwrap each element
        else:
            return [unwrap_r_plotly(item, key) for item in obj]
    else:
        return obj


def clean_plotly_trace(trace):
    """
    Remove R-specific properties that aren't valid in standard Plotly.
    
    Args:
        trace: A trace dictionary
        
    Returns:
        Cleaned trace dictionary
    """
    if not isinstance(trace, dict):
        return trace
    
    # R-specific properties to remove at trace level
    invalid_trace_props = {'frame', 'attrs', 'visdat'}
    
    # Properties that shouldn't have 'opacity' as nested property
    nested_objects = {'line', 'marker', 'error_x', 'error_y'}
    
    cleaned = {}
    for key, value in trace.items():
        if key in invalid_trace_props:
            continue
        
        # Recursively clean nested objects
        if key in nested_objects and isinstance(value, dict):
            cleaned_nested = {}
            for nested_key, nested_value in value.items():
                # Skip invalid nested properties
                if nested_key == 'opacity' and key in {'line'}:
                    continue
                cleaned_nested[nested_key] = nested_value
            cleaned[key] = cleaned_nested
        else:
            cleaned[key] = value
    
    return cleaned


def clean_plotly_layout(layout, parent_key=None):
    """
    Remove R-specific wrapping from layout properties and fix type issues.
    
    Args:
        layout: A layout dictionary
        parent_key: The parent key to determine context
        
    Returns:
        Cleaned layout dictionary
    """
    if not isinstance(layout, dict):
        return layout
    
    # Invalid properties for specific parent contexts
    invalid_axis_props = {'standoff'}
    
    cleaned = {}
    for key, value in layout.items():
        # Skip invalid properties based on context
        if parent_key in {'xaxis', 'yaxis', 'xaxis2', 'yaxis2'} and key in invalid_axis_props:
            continue
        
        # Recursively clean nested dictionaries
        if isinstance(value, dict):
            cleaned[key] = clean_plotly_layout(value, key)
        # Unwrap single-element lists for scalar properties
        elif isinstance(value, list) and len(value) == 1 and not isinstance(value[0], (dict, list)):
            unwrapped = value[0]
            # Convert numeric strings to appropriate types for specific properties
            if key in {'weight', 'size'} and isinstance(unwrapped, str):
                try:
                    cleaned[key] = int(unwrapped)
                except ValueError:
                    cleaned[key] = unwrapped
            else:
                cleaned[key] = unwrapped
        # Convert numeric strings to appropriate types for specific properties
        elif key in {'weight', 'size'} and isinstance(value, str):
            try:
                cleaned[key] = int(value)
            except ValueError:
                cleaned[key] = value
        else:
            cleaned[key] = value
    
    return cleaned


def test_results():
    st.set_page_config(page_title="stormlit", page_icon=":rain_cloud:", layout="wide")
    if "session_id" not in st.session_state:
        init_session_state()

    st.title("Test Results")

    # Sidebar configuration
    st.sidebar.markdown("# Page Navigation")
    st.sidebar.page_link("main.py", label="Home 🏠")
    st.sidebar.page_link("pages/model_qc.py", label="Model QC")
    st.sidebar.page_link("pages/hms_results.py", label="HMS Results")
    st.sidebar.page_link("pages/ras_results.py", label="RAS Results")
    st.sidebar.page_link("pages/all_results.py", label="All Results")
    # TESTING
    st.sidebar.page_link("pages/test_page.py", label="Test Page")

    test_plot_file = "/workspace/app/tests/flow-example.json"
    if os.path.exists(test_plot_file):
        with open(test_plot_file, "r") as f:
            flow_data = json.load(f)

        # Get cleaned JSON from R service
        plot_json = get_flow_plot(flow_data, json_output_path="test_flow_input.json")
        
        # Create Plotly figure from cleaned data
        fig = go.Figure(
            data=plot_json.get("data", []),
            layout=plot_json.get("layout", {})
        )
        
        # Use st.plotly_chart for full interactivity (click events, etc.)
        plot_selection = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="lasso")

        # Handle plot selection
        if len(plot_selection["selection"]["points"]) > 0:
            selected_points = plot_selection["selection"]["points"]
            st.write("Selected points:", selected_points)
        else:
            st.write("No points selected.")
            st.write(plot_selection)

if __name__ == "__main__":
    test_results()