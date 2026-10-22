import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { GitGraph, X, ZoomIn, ZoomOut } from "lucide-react";
import { useCorpusGraph } from "../../api/hooks/useResearch";
import { useAppStore } from "../../store/app";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import type { GraphNode, GraphEdge } from "../../types/api";

interface D3Node extends d3.SimulationNodeDatum, GraphNode {}
interface D3Link extends d3.SimulationLinkDatum<D3Node> {
  type: string;
}

const NODE_COLORS: Record<string, string> = {
  Article: "#d4a017",
  Case: "#60a5fa",
  Clause: "#a78bfa",
  Amendment: "#34d399",
};

export function CitationGraph() {
  const { activeCorpusId, citationGraphOpen, setCitationGraphOpen } = useAppStore();
  const { data: graph, isLoading } = useCorpusGraph(activeCorpusId);
  const svgRef = useRef<SVGSVGElement>(null);
  const [transform, setTransform] = useState({ k: 1, x: 0, y: 0 });

  useEffect(() => {
    if (!graph || !svgRef.current) return;
    const el = svgRef.current;
    const width = el.clientWidth || 600;
    const height = el.clientHeight || 400;

    const svg = d3.select(el);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform.toString());
        setTransform(event.transform);
      });
    svg.call(zoom);

    const nodes: D3Node[] = graph.nodes.map((n) => ({ ...n }));
    const links: D3Link[] = graph.edges.map((e: GraphEdge) => ({
      source: e.source,
      target: e.target,
      type: e.type,
    }));

    const simulation = d3
      .forceSimulation<D3Node>(nodes)
      .force(
        "link",
        d3
          .forceLink<D3Node, D3Link>(links)
          .id((d) => d.id)
          .distance(80),
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide(20));

    // Edges
    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-width", 1)
      .attr("stroke-opacity", 0.6)
      .attr("marker-end", "url(#arrow)");

    // Arrow marker
    svg
      .append("defs")
      .append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 18)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "#475569");

    // Nodes
    const node = g
      .append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .call(d3.drag<SVGGElement, D3Node>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }) as any);

    node
      .append("circle")
      .attr("r", 8)
      .attr("fill", (d) => NODE_COLORS[d.type] ?? "#94a3b8")
      .attr("stroke", "#1e293b")
      .attr("stroke-width", 2);

    node
      .append("text")
      .attr("dy", "0.35em")
      .attr("dx", 11)
      .attr("font-size", 9)
      .attr("fill", "#94a3b8")
      .text((d) => d.label.slice(0, 20));

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as D3Node).x ?? 0)
        .attr("y1", (d) => (d.source as D3Node).y ?? 0)
        .attr("x2", (d) => (d.target as D3Node).x ?? 0)
        .attr("y2", (d) => (d.target as D3Node).y ?? 0);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => { simulation.stop(); };
  }, [graph]);

  if (!citationGraphOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70">
      <div className="flex flex-col w-[90vw] h-[80vh] rounded-xl border border-slate-700 bg-slate-900 overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3 shrink-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <GitGraph className="h-4 w-4 text-gold-400" />
            Citation Graph
          </div>
          <div className="flex items-center gap-2">
            {/* Legend */}
            <div className="flex items-center gap-3 mr-4">
              {Object.entries(NODE_COLORS).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-xs text-slate-500">{type}</span>
                </div>
              ))}
            </div>
            <Button variant="ghost" size="sm" onClick={() => setCitationGraphOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Graph */}
        <div className="flex-1 relative">
          {isLoading ? (
            <div className="flex h-full items-center justify-center">
              <Spinner className="h-8 w-8" />
            </div>
          ) : !graph || graph.nodes.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-slate-600">
              <GitGraph className="mb-3 h-10 w-10" />
              <p className="text-sm">No graph data for this corpus</p>
            </div>
          ) : (
            <svg ref={svgRef} className="w-full h-full" />
          )}

          {/* Zoom indicator */}
          <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded bg-slate-800 border border-slate-700 px-2 py-1">
            <ZoomOut className="h-3.5 w-3.5 text-slate-500" />
            <span className="text-xs text-slate-400">{(transform.k * 100).toFixed(0)}%</span>
            <ZoomIn className="h-3.5 w-3.5 text-slate-500" />
          </div>
        </div>
      </div>
    </div>
  );
}
