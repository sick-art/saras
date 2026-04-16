/**
 * Path-based navigation/mutation helpers for the agent schema tree.
 *
 * A "path" is a string like:
 *   "" (root)
 *   "persona"
 *   "tools[2]"
 *   "tools[2].inputs[0]"
 *   "conditions[0].goals[1].slots[0]"
 *
 * Used by the OutlineTree (selection) and NodeForm (read/write the selected node).
 */

export type Path = string

const SEGMENT_RE = /([a-z_]+)(\[(\d+)\])?/i

interface Segment {
  key: string
  index?: number
}

export function parsePath(path: Path): Segment[] {
  if (!path) return []
  return path.split(".").map(part => {
    const m = part.match(SEGMENT_RE)
    if (!m) throw new Error(`Invalid path segment: ${part}`)
    return {
      key: m[1],
      index: m[3] ? Number(m[3]) : undefined,
    }
  })
}

export function pathSegments(path: Path): Segment[] {
  return parsePath(path)
}

export function joinPath(parent: Path, segment: string): Path {
  return parent ? `${parent}.${segment}` : segment
}

export function parentPath(path: Path): Path {
  const idx = path.lastIndexOf(".")
  return idx === -1 ? "" : path.slice(0, idx)
}

export function lastSegment(path: Path): Segment | null {
  const segs = parsePath(path)
  return segs.length > 0 ? segs[segs.length - 1] : null
}

/** Get a value at a path, or undefined if missing. */
export function getNodeAtPath(root: unknown, path: Path): unknown {
  if (!path) return root
  const segs = parsePath(path)
  let node: unknown = root
  for (const seg of segs) {
    if (node == null || typeof node !== "object") return undefined
    const next = (node as Record<string, unknown>)[seg.key]
    if (seg.index !== undefined) {
      if (!Array.isArray(next)) return undefined
      node = next[seg.index]
    } else {
      node = next
    }
  }
  return node
}

/**
 * Immutably set a value at a path. Returns a new root with the change applied.
 * Creates intermediate objects/arrays as needed.
 */
export function setNodeAtPath<T>(root: T, path: Path, value: unknown): T {
  if (!path) return value as T
  const segs = parsePath(path)
  return setRecursive(root, segs, 0, value) as T
}

function setRecursive(node: unknown, segs: Segment[], i: number, value: unknown): unknown {
  if (i >= segs.length) return value

  const seg = segs[i]
  const obj = (node && typeof node === "object" && !Array.isArray(node))
    ? { ...(node as Record<string, unknown>) }
    : {}

  if (seg.index !== undefined) {
    const arr = Array.isArray(obj[seg.key]) ? [...(obj[seg.key] as unknown[])] : []
    arr[seg.index] = setRecursive(arr[seg.index], segs, i + 1, value)
    obj[seg.key] = arr
  } else {
    obj[seg.key] = setRecursive(obj[seg.key], segs, i + 1, value)
  }
  return obj
}

/**
 * Immutably delete a value at a path. For array elements, splices out the index.
 * For object keys, deletes the key. Returns a new root.
 */
export function deleteNodeAtPath<T>(root: T, path: Path): T {
  if (!path) return root
  const segs = parsePath(path)
  return deleteRecursive(root, segs, 0) as T
}

function deleteRecursive(node: unknown, segs: Segment[], i: number): unknown {
  const seg = segs[i]
  if (!seg) return node

  if (i === segs.length - 1) {
    // At the leaf — perform the deletion
    if (seg.index !== undefined) {
      const obj = node && typeof node === "object" ? { ...(node as Record<string, unknown>) } : {}
      const arr = Array.isArray(obj[seg.key]) ? [...(obj[seg.key] as unknown[])] : []
      arr.splice(seg.index, 1)
      obj[seg.key] = arr
      return obj
    } else {
      const obj = node && typeof node === "object" ? { ...(node as Record<string, unknown>) } : {}
      delete obj[seg.key]
      return obj
    }
  }

  // Recurse deeper
  const obj = (node && typeof node === "object" && !Array.isArray(node))
    ? { ...(node as Record<string, unknown>) }
    : {}
  if (seg.index !== undefined) {
    const arr = Array.isArray(obj[seg.key]) ? [...(obj[seg.key] as unknown[])] : []
    arr[seg.index] = deleteRecursive(arr[seg.index], segs, i + 1)
    obj[seg.key] = arr
  } else {
    obj[seg.key] = deleteRecursive(obj[seg.key], segs, i + 1)
  }
  return obj
}

/**
 * Append an item to an array at the given parent path.
 * Returns [newRoot, pathOfNewItem].
 */
export function appendArrayItem<T>(
  root: T,
  arrayPath: Path,
  item: unknown,
): [T, Path] {
  const arr = getNodeAtPath(root, arrayPath)
  const currentLength = Array.isArray(arr) ? arr.length : 0
  const newPath = `${arrayPath}[${currentLength}]`
  const newRoot = setNodeAtPath(root, newPath, item)
  return [newRoot, newPath]
}

/** Move an array item from one index to another. Returns new root. */
export function moveArrayItem<T>(
  root: T,
  arrayPath: Path,
  fromIndex: number,
  toIndex: number,
): T {
  const arr = getNodeAtPath(root, arrayPath)
  if (!Array.isArray(arr)) return root
  const next = [...arr]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return setNodeAtPath(root, arrayPath, next)
}
