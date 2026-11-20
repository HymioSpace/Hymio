export type WorkflowNodeLike = {
  id: string;
  depends_on: string[];
};

export type WorkflowEdgeLike = { from: string; to: string };

export function workflowLayers(nodes: WorkflowNodeLike[], edges: WorkflowEdgeLike[]) {
  const byID = new Map(nodes.map((node) => [node.id, node]));
  const dependencies = new Map(
    nodes.map((node) => [
      node.id,
      new Set([
        ...node.depends_on,
        ...edges.filter((edge) => edge.to === node.id).map((edge) => edge.from),
      ]),
    ]),
  );
  const depth = new Map<string, number>();
  function visit(id: string, visiting: Set<string>): number {
    const known = depth.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const value = Math.max(
      0,
      ...[...(dependencies.get(id) || [])]
        .filter((dependency) => byID.has(dependency))
        .map((dependency) => visit(dependency, visiting) + 1),
    );
    visiting.delete(id);
    depth.set(id, value);
    return value;
  }
  nodes.forEach((node) => visit(node.id, new Set()));
  const layers: WorkflowNodeLike[][] = [];
  nodes.forEach((node) => {
    const index = depth.get(node.id) || 0;
    (layers[index] ||= []).push(node);
  });
  return layers.filter(Boolean);
}
