import os
import requests
import json
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()


def clean_r_plotly_object(obj, parent_key=None, trace_context=False):
    """
    Recursively clean R plotly objects to convert them to standard Plotly format.
    
    This handles:
    - Unwrapping single-element arrays for scalar properties
    - Removing invalid R-specific properties
    - Converting string numbers to appropriate types
    - Preserving coordinate arrays (x, y, z, etc.)
    
    Args:
        obj: The object to clean (dict, list, or primitive)
        parent_key: The parent key for context
        trace_context: Whether we're inside a trace object
        
    Returns:
        Cleaned object
    """
    # Properties that should remain as arrays (only in trace data context)
    trace_array_fields = {'x', 'y', 'z', 'text', 'hovertext', 'ids', 'customdata', 
                         'lat', 'lon', 'locations', 'values', 'labels'}
    
    # Invalid top-level properties to remove
    invalid_props = {'frame', 'attrs', 'visdat', 'standoff'}
    
    # Invalid nested properties by parent context
    invalid_nested_props = {
        'line': {'opacity'},  # line.opacity is invalid in Plotly
        'marker': set(),
    }
    
    # Properties that should be integers
    int_props = {'weight', 'size', 'width'}
    
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            # Skip invalid top-level properties
            if key in invalid_props:
                continue
            
            # Skip invalid nested properties based on parent context
            if parent_key in invalid_nested_props and key in invalid_nested_props[parent_key]:
                continue
            
            # Check if this is an axis context and skip standoff
            is_axis = parent_key and parent_key.startswith(('xaxis', 'yaxis'))
            if is_axis and key == 'standoff':
                continue
            
            # Recursively clean all values (dicts, lists, primitives)
            cleaned_value = clean_r_plotly_object(value, key, trace_context or parent_key == 'data')
            
            # Convert string numbers to int for specific properties
            if key in int_props and isinstance(cleaned_value, str):
                try:
                    cleaned_value = int(cleaned_value)
                except ValueError:
                    pass
            
            cleaned[key] = cleaned_value
        
        return cleaned
    
    elif isinstance(obj, list):
        # Keep coordinate arrays but unwrap their nested single-element arrays
        # Only preserve as arrays if we're in a trace context (not layout)
        if trace_context and parent_key in trace_array_fields:
            result = []
            for item in obj:
                if isinstance(item, list) and len(item) == 1 and not isinstance(item[0], (dict, list)):
                    result.append(item[0])
                else:
                    result.append(clean_r_plotly_object(item, parent_key, trace_context))
            return result
        
        # Unwrap single-element lists for scalar properties (including layout properties)
        # Check that the single element is not a dict or list
        if len(obj) == 1:
            first_elem = obj[0]
            # Only unwrap if the element is not a dict or list
            if not isinstance(first_elem, (dict, list)):
                return first_elem
        
        # For multi-element lists, check if all elements are single-element arrays
        # and unwrap them (common in R plotly for data arrays)
        if len(obj) > 1 and all(isinstance(item, list) and len(item) == 1 for item in obj):
            return [item[0] if isinstance(item, list) and len(item) == 1 else item for item in obj]
        
        # Recursively clean list elements
        return [clean_r_plotly_object(item, parent_key, trace_context) for item in obj]
    
    else:
        return obj


def get_flow_plot(
    data: Dict[str, Any],
    json_output_path: str,
    return_html: bool = False,
) -> Dict[str, Any] | str:
    """
    Generate a flow plot by sending data to the R service API.
    
    This function makes a POST request to the R service's realization/flows endpoint
    with the provided data, saves the input data as JSON, and returns the plot data
    as a cleaned JSON object or HTML.
    
    Args:
        data (Dict[str, Any]): Dictionary containing the flow data to plot.
            Should match the expected schema for the /api/realization/flows endpoint.
        json_output_path (str): Path where the input data JSON should be saved.
        return_html (bool): If True, returns HTML instead of JSON. Default False.
    
    Returns:
        Dict[str, Any] | str: The cleaned Plotly figure data as a JSON object or HTML string.
    
    Raises:
        requests.RequestException: If the API request fails.
        ValueError: If R_SERVICE_URL is not set.
    
    Example:
        >>> # Get as cleaned JSON for Plotly
        >>> plot_json = get_flow_plot(flow_data, "flow_input.json")
        >>> import plotly.graph_objects as go
        >>> fig = go.Figure(data=plot_json['data'], layout=plot_json['layout'])
    """
    # Get R service URL from environment variable
    service = os.getenv("R_SERVICE")
    base_url = f"http://{service}"
    
    if not base_url or service is None:
        raise ValueError(
            "R service URL not configured. Set R_SERVICE environment variable."
        )
    
    # Remove trailing slash if present
    base_url = base_url.rstrip("/")
    
    # Create request data (don't modify the original)
    request_data = data.copy()
    request_data["json"] = True
        
    
    # Save original input data to JSON file (not the request data)
    output_file = json_output_path
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    # Construct the full API endpoint
    endpoint = f"{base_url}/api/realization/flows"
    
    # Make POST request with JSON data
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(
        endpoint,
        headers=headers,
        json=request_data,
        timeout=30
    )
    
    # Raise an exception for bad status codes
    response.raise_for_status()
    
    # Return HTML or cleaned JSON based on request
    if return_html:
        # save to HTML file for inspection
        file = "r_service_response.html"
        with open(file, "w", encoding="utf-8") as f:
            f.write(response.text)
        return response.text
    else:
        # Check if response is actually JSON
        content_type = response.headers.get('Content-Type', '')
        
        # If response is HTML, it means the R service didn't return JSON
        # This happens when json flag in request data is not properly set
        if 'text/html' in content_type or not response.text.strip().startswith('{'):
            raise ValueError(
                "R service returned HTML instead of JSON. "
                "Make sure the input data has 'json': true set. "
                f"Response content type: {content_type}"
            )
        
        try:
            # Parse the JSON response
            plot_data = response.json()
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse R service response as JSON. "
                f"Response starts with: {response.text[:200]}"
            ) from e
        
        # Clean the R plotly object to standard Plotly format
        cleaned_data = clean_r_plotly_object(plot_data, parent_key=None, trace_context=False)
        
        # Remove R-specific top-level keys that aren't part of standard Plotly
        r_specific_keys = {'visdat', 'cur_data', 'attrs', 'base_url', 'shinyEvents', 
                          'highlight', 'source', 'config'}
        for key in r_specific_keys:
            cleaned_data.pop(key, None)
        
        # Ensure we only return data and layout (the essential parts for Plotly)
        plotly_figure = {
            'data': cleaned_data.get('data', []),
            'layout': cleaned_data.get('layout', {})
        }
        
        return plotly_figure
