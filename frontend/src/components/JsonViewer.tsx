type JsonViewerProps = {
  data: unknown
  title?: string
}

export function JsonViewer({ data, title = 'JSON payload' }: JsonViewerProps) {
  return (
    <figure className="json-viewer" aria-label={title}>
      <figcaption>{title}</figcaption>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </figure>
  )
}
