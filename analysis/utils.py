import plotly.graph_objects as go
import pandas as pd


def show_interactive_lines(df_plot: pd.DataFrame, title: str, y_label: str, series_map: list) -> None:
    """Render an interactive Plotly line chart with built-in hover tooltips."""
    fig = go.Figure()
    for label, column in series_map:
        fig.add_trace(
            go.Scatter(
                x=df_plot.index,
                y=df_plot[column],
                mode='lines',
                name=label,
                hovertemplate='%{x|%Y-%m-%d %H:%M}<br>%{y:.4f}<extra>' + label + '</extra>',
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title='Datetime',
        yaxis_title=y_label,
        hovermode='x unified',
        template='plotly_white',
    )
    fig.show()
