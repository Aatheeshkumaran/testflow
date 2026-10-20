"""Builds Chart.js configs on the server so views stay simple. static/js/charts.js renders them."""
VIOLET, NAVY, GREEN, AMBER, RED, SLATE, SKY = "#6d4aff", "#1b2142", "#16a34a", "#f59e0b", "#e5484d", "#94a3b8", "#0ea5e9"


def _num(v):
    return None if v is None else round(float(v), 1)


def _opts(percent=False, y_max=None, stacked=False, horizontal=False, legend=True):
    value_axis = {"beginAtZero": True, "grace": 0, **({"max": y_max} if y_max else {}), **({"stacked": True} if stacked else {})}
    cat_axis = {**({"stacked": True} if stacked else {}), "grid": {"display": False}}
    return {
        "responsive": True, "maintainAspectRatio": False, "spanGaps": True,
        "indexAxis": "y" if horizontal else "x",
        "scales": {("x" if horizontal else "y"): value_axis, ("y" if horizontal else "x"): cat_axis},
        "plugins": {"legend": {"display": legend, "position": "bottom"}, "testflow": {"percent": percent}},
    }


def line_chart(labels, datasets, percent=True):
    ds = [{
        "label": d["label"], "data": [_num(x) for x in d["data"]], "borderColor": d.get("color", VIOLET),
        "backgroundColor": d.get("color", VIOLET), "tension": 0.3, "pointRadius": d.get("points", 4),
        "borderDash": [6, 4] if d.get("dashed") else [], "borderWidth": 2,
    } for d in datasets]
    return {"type": "line", "data": {"labels": labels, "datasets": ds},
            "options": _opts(percent=percent, y_max=100 if percent else None, legend=len(ds) > 1)}


def bar_chart(labels, datasets, percent=False, stacked=False, horizontal=False, y_max=None):
    ds = [{"label": d["label"], "data": [_num(x) for x in d["data"]], "backgroundColor": d.get("color", VIOLET),
           "borderRadius": 4, "maxBarThickness": 38} for d in datasets]
    return {"type": "bar", "data": {"labels": labels, "datasets": ds},
            "options": _opts(percent=percent, y_max=100 if percent else y_max, stacked=stacked,
                             horizontal=horizontal, legend=len(ds) > 1)}


def doughnut_chart(labels, values, colors):
    return {"type": "doughnut",
            "data": {"labels": labels, "datasets": [{"data": values, "backgroundColor": colors, "borderWidth": 0}]},
            "options": {"responsive": True, "maintainAspectRatio": False, "cutout": "62%",
                        "plugins": {"legend": {"position": "bottom"}, "testflow": {"percent": False}}}}
