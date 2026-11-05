export function MeshBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0 bg-linear-to-br from-indigo-50 via-white to-violet-50" />
      <div className="absolute top-0 left-1/4 h-96 w-96 rounded-full bg-indigo-200 opacity-30 blur-3xl" />
      <div className="absolute right-1/4 bottom-0 h-96 w-96 rounded-full bg-violet-200 opacity-30 blur-3xl" />
    </div>
  )
}
