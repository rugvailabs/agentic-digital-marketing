/**
 * What an asset is called, in words.
 *
 * Lived in Studio while the Post tab drew its own image grid. The grid
 * moved to the Desk's assets rail and the labels had to go with it, or the
 * rail would have gone on captioning its cards "square:poster" — which, as
 * the comment below has said since the first version, tells nobody
 * anything.
 */

/** Full template names. The renderer sends one in `meta.label`; this is the
 *  fallback for assets rendered before it did. */
const TEMPLATE_LABELS: Record<string, string> = {
  poster: 'Poster',
  split: 'Split panel',
  wire: 'Wire',
  'bold-type': 'Bold type',
  'split-panel': 'Split panel',
  'flat-colour': 'Flat colour',
}

export function templateLabel(asset: {
  variant: string
  meta_json: Record<string, unknown>
}): string {
  const label = asset.meta_json?.label
  if (typeof label === 'string' && label) return label
  const template = asset.variant.split(':')[1] ?? asset.variant
  return TEMPLATE_LABELS[template] ?? template.replace(/-/g, ' ')
}

export function dimensions(asset: { meta_json: Record<string, unknown> }): string {
  const { width, height } = asset.meta_json as { width?: number; height?: number }
  return width && height ? `${width}×${height}` : ''
}
