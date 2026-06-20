from __future__ import annotations

import json
import re

from .models import AnalysisResult, CausalLink


EXPANSIONS = {
    "hba1c": "Glycated haemoglobin (HbA1c)",
    "egfr": "Estimated glomerular filtration rate (eGFR)",
    "copd": "Chronic obstructive pulmonary disease (COPD)",
    "ecg": "Electrocardiogram (ECG)",
    "bnp": "B-type natriuretic peptide (BNP)",
    "crp": "C-reactive protein (CRP)",
    "tsh": "Thyroid-stimulating hormone (TSH)",
}


def full_name(value: str) -> str:
    output = value
    for abbreviation, expanded in EXPANSIONS.items():
        output = re.sub(rf"\b{re.escape(abbreviation)}\b", expanded, output, flags=re.I)
    output = output.strip()
    return output[:1].upper() + output[1:] if output else output


def future_concern(result: AnalysisResult, link: CausalLink | None = None) -> str:
    selected_link = link or (result.causal_links[0] if result.causal_links else None)
    if selected_link:
        if selected_link.display_concern:
            return selected_link.display_concern
        implication = selected_link.implication
        replacements = {
            "Higher follow-up priority and risk of diabetes complications": "Possible future diabetes-related complications",
            "Possible medication and electrolyte safety concern": "Possible future electrolyte or medication-related complication",
            "Urgent review is required because symptoms and ECG findings occur together": "Possible future acute heart-related complication",
            "Urgent review is required because symptoms and electrocardiogram findings occur together": "Possible future acute heart-related complication",
            "Reduced oxygenation increases urgency": "Possible future breathing deterioration",
            "Higher risk of deterioration or readmission": "Possible future heart failure deterioration",
            "Low haemoglobin requires investigation and monitoring": "Possible future worsening anaemia",
            "Increased cardiovascular risk without documented acute instability": "Possible future heart or blood-vessel complication",
            "Routine medication adjustment may be required": "Possible future thyroid-related symptoms",
        }
        return replacements.get(implication, full_name(implication))
    return "Future health concern requires clinical review"


def causal_journey_html(
    result: AnalysisResult,
    selected_link: CausalLink | None = None,
) -> str:
    primary_link = selected_link or (result.causal_links[0] if result.causal_links else None)
    patient_name = str(result.patient_details.get("name", "Patient"))
    source = (
        ", ".join(primary_link.source_documents)
        if primary_link and primary_link.source_documents
        else "Current clinical record"
    )
    source = f"{patient_name} · {source}"
    evidence = full_name(primary_link.finding) if primary_link else "No specific warning signal identified"
    interpretation = (
        full_name(primary_link.display_interpretation or primary_link.meaning)
        if primary_link
        else "Human review of extracted evidence"
    )
    future = future_concern(result, primary_link)
    action = full_name(primary_link.action) if primary_link else full_name(result.recommended_action)

    nodes = [
        {"id": "source", "stage": "Source document", "label": source, "column": 0.03, "y": 190, "mobileX": 8, "mobileY": 20, "color": "#557A68"},
        {"id": "evidence", "stage": "Observed evidence", "label": evidence, "column": 0.36, "y": 105, "mobileX": 178, "mobileY": 20, "color": "#327A96"},
        {"id": "interpretation", "stage": "Rule-supported interpretation", "label": interpretation, "column": 0.36, "y": 285, "mobileX": 8, "mobileY": 182, "color": "#C27A31"},
        {"id": "future", "stage": "Potential concern · hypothesis", "label": future, "column": 0.69, "y": 105, "mobileX": 178, "mobileY": 182, "color": "#B54D4D"},
        {"id": "action", "stage": "Proposed intervention", "label": action, "column": 0.69, "y": 285, "mobileX": 93, "mobileY": 354, "color": "#6B5A8E"},
    ]
    edges = [
        {"from": "source", "to": "evidence", "label": "contains", "kind": "observed"},
        {"from": "evidence", "to": "interpretation", "label": "matched by transparent rule", "kind": "assumption"},
        {"from": "interpretation", "to": "future", "label": "may indicate", "kind": "assumption"},
        {"from": "action", "to": "future", "label": "intervention hypothesis", "reverse": True, "kind": "intervention"},
    ]

    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        * {{box-sizing:border-box}}
        body {{
          margin:0; background:#F7F9FA; color:#17212B;
          font-family:"Fragment Core Roman","Fragment Core",Georgia,serif;
        }}
        #graph {{
          position:relative; width:100%; height:545px; overflow:hidden;
          border:1px solid #D8E0E5; background:#FFFFFF;
        }}
        svg {{position:absolute; inset:0; width:100%; height:100%; pointer-events:none}}
        .node {{
          position:absolute; width:210px; min-height:96px; padding:13px 14px 12px;
          border:1px solid #D6DEE3; border-top:4px solid var(--color);
          background:#FFFFFF; cursor:grab; user-select:none; touch-action:none;
          box-shadow:0 3px 12px rgba(23,33,43,.07);
        }}
        .node:active {{cursor:grabbing; box-shadow:0 7px 20px rgba(23,33,43,.14)}}
        .stage {{font-size:11px; text-transform:uppercase; color:#71808A; margin-bottom:7px}}
        .label {{font-size:15px; line-height:1.3; overflow-wrap:anywhere}}
        .edge-label {{
          position:absolute; transform:translate(-50%,-50%); background:#FFFFFF;
          padding:2px 6px; color:#697780; font-size:10px; pointer-events:none;
          white-space:nowrap;
        }}
        .hint {{position:absolute; left:14px; bottom:10px; font-size:11px; color:#85919A}}
        .relation-key {{position:absolute; left:12px; right:12px; bottom:24px; color:#6F7B84; font-size:10px; text-align:center}}
        @media(max-width:760px) {{
          .node {{width:160px; min-height:98px; padding:10px 11px}}
          .label {{font-size:12.5px; line-height:1.23}}
          .stage {{font-size:9.5px}}
          .edge-label {{display:none}}
          .hint {{bottom:8px}}
        }}
      </style>
    </head>
    <body>
      <div id="graph">
        <svg id="edges">
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto">
              <polygon points="0 0, 8 3.5, 0 7" fill="#95A2AA"></polygon>
            </marker>
          </defs>
        </svg>
        <div class="relation-key">Solid: documented relationship · Dashed: expert-rule assumption · Dotted: intervention hypothesis</div>
        <div class="hint">Nodes are draggable</div>
      </div>
      <script>
        const nodeData = {nodes_json};
        const edgeData = {edges_json};
        const graph = document.getElementById("graph");
        const svg = document.getElementById("edges");
        const elements = {{}};

        nodeData.forEach(n => {{
          const el = document.createElement("div");
          el.className = "node";
          el.dataset.id = n.id;
          const mobile = graph.clientWidth < 650;
          el.style.left = (mobile ? n.mobileX : Math.max(8, Math.min(graph.clientWidth - 218, graph.clientWidth * n.column))) + "px";
          el.style.top = (mobile ? n.mobileY : n.y) + "px";
          el.style.setProperty("--color", n.color);
          el.innerHTML = `<div class="stage">${{escapeHtml(n.stage)}}</div><div class="label">${{escapeHtml(n.label)}}</div>`;
          graph.appendChild(el);
          elements[n.id] = el;
          makeDraggable(el);
        }});

        const lines = edgeData.map(e => {{
          const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
          line.setAttribute("stroke", "#95A2AA");
          line.setAttribute("stroke-width", "1.6");
          if (e.kind === "assumption") line.setAttribute("stroke-dasharray", "8 5");
          if (e.kind === "intervention") line.setAttribute("stroke-dasharray", "2 5");
          line.setAttribute("marker-end", "url(#arrow)");
          svg.appendChild(line);
          const label = document.createElement("div");
          label.className = "edge-label";
          label.textContent = e.label;
          graph.appendChild(label);
          return {{...e, line, label}};
        }});

        function escapeHtml(value) {{
          return value.replace(/[&<>"']/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[m]));
        }}
        function center(el) {{
          return {{x:el.offsetLeft + el.offsetWidth/2, y:el.offsetTop + el.offsetHeight/2}};
        }}
        function updateEdges() {{
          lines.forEach(e => {{
            const from = center(elements[e.reverse ? e.to : e.from]);
            const to = center(elements[e.reverse ? e.from : e.to]);
            e.line.setAttribute("x1", from.x); e.line.setAttribute("y1", from.y);
            e.line.setAttribute("x2", to.x); e.line.setAttribute("y2", to.y);
            e.label.style.left = ((from.x + to.x)/2) + "px";
            e.label.style.top = ((from.y + to.y)/2) + "px";
          }});
        }}
        function makeDraggable(el) {{
          let dx=0, dy=0, dragging=false;
          el.addEventListener("pointerdown", event => {{
            dragging=true; el.setPointerCapture(event.pointerId);
            dx=event.clientX-el.offsetLeft; dy=event.clientY-el.offsetTop;
          }});
          el.addEventListener("pointermove", event => {{
            if(!dragging) return;
            const maxX=graph.clientWidth-el.offsetWidth-8;
            const maxY=graph.clientHeight-el.offsetHeight-8;
            el.style.left=Math.max(8,Math.min(maxX,event.clientX-dx))+"px";
            el.style.top=Math.max(8,Math.min(maxY,event.clientY-dy))+"px";
            updateEdges();
          }});
          el.addEventListener("pointerup", ()=>dragging=false);
          el.addEventListener("pointercancel", ()=>dragging=false);
          el.addEventListener("mousedown", event => {{
            dragging=true;
            dx=event.clientX-el.offsetLeft; dy=event.clientY-el.offsetTop;
          }});
          document.addEventListener("mousemove", event => {{
            if(!dragging) return;
            const maxX = graph.clientWidth - el.offsetWidth - 8;
            const maxY = graph.clientHeight - el.offsetHeight - 8;
            el.style.left = Math.max(8, Math.min(maxX, event.clientX-dx)) + "px";
            el.style.top = Math.max(8, Math.min(maxY, event.clientY-dy)) + "px";
            updateEdges();
          }});
          document.addEventListener("mouseup", ()=>dragging=false);
        }}
        updateEdges();
        window.addEventListener("resize", updateEdges);
      </script>
    </body>
    </html>
    """
