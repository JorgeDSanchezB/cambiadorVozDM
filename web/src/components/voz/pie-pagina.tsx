// Pie de página — fijo al fondo (regla de layout), solo con el adorno
// ornamental de la forja. Sin texto: el usuario final no necesita metadatos.

export function PiePagina() {
  return (
    <footer className="mt-auto border-t border-border/60 bg-card/30 backdrop-blur-sm">
      <div className="mx-auto max-w-6xl px-4 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-center gap-3" aria-hidden="true">
          <span className="h-px max-w-28 flex-1 bg-gradient-to-r from-transparent to-border" />
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/40" />
            <span className="relative inline-flex size-2 rounded-full bg-primary/70" />
          </span>
          <span className="h-px max-w-28 flex-1 bg-gradient-to-l from-transparent to-border" />
        </div>
      </div>
    </footer>
  )
}
