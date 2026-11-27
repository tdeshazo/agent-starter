// Teaching model for read_file, using /workspace as a simulated working directory.
function evaluateAtlasReadFile({path, start, end, kind, size, selectedBytes}) {
  const steps = [];
  const pass = (gate, detail) => steps.push({gate, status: "pass", detail});
  const fail = (gate, detail) => {
    steps.push({gate, status: "fail", detail});
    return steps;
  };
  const wholeFileLimit = 4096;
  const rangeFileLimit = 1024 * 1024;
  const workspace = "workspace";

  const ranged = start.trim() !== "";
  if (ranged !== (end.trim() !== "")) {
    return fail("Line range", "Provide both start_line and end_line together.");
  }
  if (ranged && (
    !/^\+?\d+$/.test(start.trim()) || !/^\+?\d+$/.test(end.trim()) ||
    Number(start) < 1 || Number(start) > Number(end)
  )) {
    return fail("Line range", "Line numbers must be positive integers with start_line at most end_line.");
  }
  pass("Line range", ranged ? `Inclusive lines ${start} through ${end}.` : "Whole-file read.");

  const segments = path.startsWith("/") ? [] : [workspace];
  for (const segment of path.split("/")) {
    if (segment === "..") segments.pop();
    else if (segment && segment !== ".") segments.push(segment);
  }
  if (kind === "symlink_outside" || segments[0] !== workspace) {
    return fail("Workspace confinement", "The resolved path is outside /workspace.");
  }
  const parts = kind === "symlink_env" ? [".env"] : segments.slice(1);
  pass("Workspace confinement", "The resolved path stays inside /workspace.");

  const last = parts[parts.length - 1];
  const allowedEnv = [".env.example", ".env.sample", ".env.template"];
  if (parts.includes(".git") || last === ".env" || (last?.startsWith(".env.") && !allowedEnv.includes(last))) {
    return fail("Sensitive paths", "The resolved path is excluded.");
  }
  pass("Sensitive paths", "The resolved path passes the sensitive-path check.");

  if (!last || kind === "fifo" || kind === "dir") {
    return fail("Regular file", "The resolved path must refer to a regular file.");
  }
  pass("Regular file", "The simulated target is a regular file.");

  const limit = ranged ? rangeFileLimit : wholeFileLimit;
  if (size > limit) {
    return fail("Input bytes", `File exceeds the ${limit.toLocaleString()}-byte read limit.`);
  }
  pass("Input bytes", `The file fits within the ${limit.toLocaleString()}-byte read limit.`);

  if (kind === "binary") {
    return fail("UTF-8 decoding", "The file contains invalid UTF-8.");
  }
  pass("UTF-8 decoding", "The simulated file is valid UTF-8.");

  if (ranged) {
    if (selectedBytes !== null && selectedBytes > wholeFileLimit) {
      return fail("Selected output", "Line range exceeds the 4,096-byte read limit.");
    }
    if (selectedBytes === null && size > wholeFileLimit) {
      steps.push({gate: "Selected output", status: "unknown", detail: "Enter the selected range size in bytes to check the 4,096-byte limit."});
      return steps;
    }
    pass("Selected output", "The selected text fits within 4,096 bytes.");
  }
  return steps;
}
