import assert from "node:assert/strict";
import test from "node:test";
import { orderSpans } from "../src/trace-model.ts";

test("parents stay above children even when child timestamps are earlier", () => {
  const spans = [
    { span_id: "child", parent_span_id: "root", start_unix_nano: 1 },
    { span_id: "root", parent_span_id: null, start_unix_nano: 2 },
    { span_id: "orphan", parent_span_id: "missing", start_unix_nano: 3 },
  ];
  assert.deepEqual(
    orderSpans(spans).map(({ span, depth }) => [span.span_id, depth]),
    [
      ["root", 0],
      ["child", 1],
      ["orphan", 0],
    ],
  );
});
test("cyclic parent links cannot hide spans or recurse forever", () => {
  const spans = [
    { span_id: "a", parent_span_id: "b", start_unix_nano: 1 },
    { span_id: "b", parent_span_id: "a", start_unix_nano: 2 },
  ];
  assert.equal(orderSpans(spans).length, 2);
});
