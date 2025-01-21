import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode

cell_renderer = JsCode(
    """
    class CustomRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.innerHTML = params.value;
        }
        getGui() {
            return this.eGui;
        }
    }
    """
)

custom_css = {
    ".ag-cell": {"white-space": "normal !important", "line-height": "1.2 !important"},
}


def stylized_table(df: pd.DataFrame):
    gb = GridOptionsBuilder.from_dataframe(df)

    for column in df.columns:
        gb.configure_column(column, wrapText=True, autoHeight=True)

    gb.configure_column("Link", cellRenderer=cell_renderer)
    grid_options = gb.build()
    return AgGrid(
        df,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        custom_css=custom_css,
    )
