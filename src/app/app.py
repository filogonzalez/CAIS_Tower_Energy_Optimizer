"""Dash Energy NOC app for Databricks Apps."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import dash_bootstrap_components as dbc
import plotly.express as px
from components.layout import build_layout
from dash import Dash, Input, Output, callback, html
from db import fetch_proposals, fetch_site_status, user_context_from_headers
from flask import request

brand = os.getenv("TEO_BRAND", "IslaNet Telecom")
app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY], suppress_callback_exceptions=True)
server = app.server
app.layout = build_layout(brand)


@callback(
    Output("site-store", "data"),
    Output("proposal-store", "data"),
    Output("error-state", "children"),
    Input("refresh", "n_intervals"),
)
def refresh_data(_):
    try:
        user = user_context_from_headers(request.headers)
        sites = fetch_site_status(user)
        proposals = fetch_proposals(user)
        return sites, proposals, ""
    except Exception as exc:
        return [], [], html.Div(f"Unable to load governed data: {exc}", className="error-state")


@callback(
    Output("kpi-sites", "children"),
    Output("kpi-risk", "children"),
    Output("kpi-proposals", "children"),
    Output("stale-state", "children"),
    Output("site-map", "figure"),
    Output("benchmark-chart", "figure"),
    Input("site-store", "data"),
    Input("proposal-store", "data"),
)
def render_overview(sites, proposals):
    sites = sites or []
    proposals = proposals or []
    risk = sum(1 for row in sites if float(row.get("priority_score") or 0) >= 70)
    as_of_values = [row.get("as_of_utc") for row in sites if row.get("as_of_utc")]
    stale = (
        "No current projections" if not as_of_values else f"As of {max(as_of_values)} UTC / displayed in AST"
    )
    map_figure = px.scatter_map(
        sites,
        lat=[row.get("payload", {}).get("latitude") for row in sites],
        lon=[row.get("payload", {}).get("longitude") for row in sites],
        color="region" if sites else None,
        hover_name="site_id" if sites else None,
        zoom=7,
        height=530,
    )
    map_figure.update_layout(map_style="carto-darkmatter", margin=dict(l=0, r=0, t=0, b=0))
    benchmark = px.bar(sites, x="site_id", y="priority_score", color="score_status", height=500)
    return len(sites), risk, len(proposals), stale, map_figure, benchmark


@server.get("/health")
def health():
    return {"status": "ok", "time_utc": datetime.now(UTC).isoformat(), "synthetic": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DATABRICKS_APP_PORT", "8000")), debug=False)
