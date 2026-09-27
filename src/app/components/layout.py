"""Dark NOC layout with explicit states and five operator views."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def kpi_card(title: str, element_id: str) -> dbc.Card:
    return dbc.Card([dbc.CardHeader(title), dbc.CardBody(html.H3("—", id=element_id))], className="kpi-card")


def build_layout(brand: str):
    return dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(html.H2(f"{brand} — Energy NOC"), width=8),
                    dbc.Col(html.Div("SYNTHETIC DATA", className="synthetic-banner"), width=4),
                ]
            ),
            html.Div(id="stale-state", className="state-banner"),
            dbc.Row(
                [
                    dbc.Col(kpi_card("Sites", "kpi-sites")),
                    dbc.Col(kpi_card("Monthly Cost", "kpi-cost")),
                    dbc.Col(kpi_card("At Risk", "kpi-risk")),
                    dbc.Col(kpi_card("Open Proposals", "kpi-proposals")),
                ],
                className="g-2",
            ),
            dcc.Interval(id="refresh", interval=60_000, n_intervals=0),
            dcc.Store(id="site-store"),
            dcc.Store(id="proposal-store"),
            dbc.Tabs(
                [
                    dbc.Tab([dcc.Graph(id="site-map"), html.Div(id="site-flyout")], label="Map / Mapa"),
                    dbc.Tab(
                        [dcc.Graph(id="benchmark-chart"), html.Div(id="bulk-plans")], label="Benchmarking"
                    ),
                    dbc.Tab(
                        [html.Div(id="agent-traces"), html.Div(id="approval-queue")],
                        label="Agent & Approvals",
                    ),
                    dbc.Tab(
                        [dcc.Graph(id="resilience-chart"), html.Div(id="storm-summary")],
                        label="Outage Resilience",
                    ),
                    dbc.Tab(
                        [
                            dcc.Input(id="audit-search", placeholder="Search audit"),
                            html.Div(id="audit-table"),
                        ],
                        label="Audit",
                    ),
                ],
                className="mt-3",
            ),
            html.Div(id="error-state", role="alert"),
        ],
        fluid=True,
    )
