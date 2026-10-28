'use client'

import type { ContentAsset, ContentJob } from '@trendforge/types'
import { useQuery } from '@tanstack/react-query'

import { EmptyState } from '@/components/Empty'
import { SectionLabel } from '@/components/house'
import { AssetCard } from '@/components/desk/AssetCard'
import { dimensions, templateLabel } from '@/components/desk/assetLabels'
import { Skeleton } from '@/components/Skeleton'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020'

/**
 * Everything already made for this topic, as cards, beside the Desk.
 *
 * It used to live inside the Post tab, which meant the images existed only
 * while you were looking at the tab that made them — switch to Evidence and
 * the work disappeared, and the Desk's right-hand half was empty page. A
 * rail is the honest shape: the assets belong to the topic, not to a tab.
 *
 * Fixed 420px. The posters are 1:1 and 9:16 and a column that reflows would
 * resize every one of them on a window drag.
 */
export function DeskRail({ trendId }: { trendId: number }) {
  const post = useJobFor(trendId, 'post')
  const reel = useJobFor(trendId, 'reel')

  const images = (post.data?.assets ?? []).filter((a) => a.kind === 'image')
  // The poster is not an asset row of its own — it is a frame of the video,
  // stored as `poster_url` on the video's meta. Looking for a 'poster' kind
  // found nothing and would have shown "nothing generated" for every topic
  // whose reel had in fact rendered.
  const video = (reel.data?.assets ?? []).find((a) => a.kind === 'video')
  const posterUrl =
    typeof video?.meta_json?.poster_url === 'string' ? video.meta_json.poster_url : null
  const loading = post.isPending || reel.isPending
  const nothing = !loading && images.length === 0 && !video

  return (
    <aside
      aria-label="Generated assets"
      className="desk:border-l desk:border-t-0 flex flex-col gap-4 border-t border-border p-5"
    >
      <SectionLabel>Assets</SectionLabel>

      {loading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="aspect-square w-full rounded-md" />
          ))}
        </div>
      ) : nothing ? (
        <EmptyState
          art="grid"
          title="Nothing generated for this topic yet."
          hint="Open the Post or Reel tab and generate one."
        />
      ) : (
        // One auto-filling grid rather than a two-column one. The rail is
        // 420px as a column and the width of the Desk when it stacks, so a
        // fixed `grid-cols-2` made the same card 190px tall in one case and
        // 480px in the other — which turned the stacked rail into a screen
        // and a half of poster. A minimum card width instead: two across in
        // the column, five when it stacks, the same size in both.
        <div className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] items-start gap-3">
          {images.map((asset) => (
            <ImageCard key={asset.id} asset={asset} jobId={post.data?.id} />
          ))}

          {/* The reel's poster rather than the video: a rail of autoplaying
              players is a different page. The card opens the file. */}
          {video ? (
            <AssetCard
              url={video.url}
              title="Reel"
              subtitle={String(video.meta_json?.label ?? 'Rendered')}
              jobId={reel.data?.id}
            >
              {posterUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={posterUrl}
                  alt="Reel poster"
                  className="aspect-[9/16] w-full bg-page object-contain"
                />
              ) : null}
            </AssetCard>
          ) : null}
        </div>
      )}
    </aside>
  )
}

function ImageCard({ asset, jobId }: { asset: ContentAsset; jobId?: number }) {
  return (
    <AssetCard
      url={asset.url}
      title={templateLabel(asset)}
      subtitle={dimensions(asset)}
      jobId={jobId}
    >
      {asset.url ? (
        /* A MinIO URL on a published port, which next/image cannot be
           configured for without pinning the dev host. */
        // eslint-disable-next-line @next/next/no-img-element
        <img src={asset.url} alt="" className="aspect-square w-full bg-page object-cover" />
      ) : null}
    </AssetCard>
  )
}

/**
 * The topic's latest job of one kind.
 *
 * react-query rather than the Desk's own polling hook: this is a read, it
 * is shared by two tabs and a rail, and the cache is what stops three
 * components fetching the same job three times. A 404 means nothing has
 * been generated yet, which is an answer and not an error — returning null
 * for it keeps the empty state out of the error path.
 */
function useJobFor(trendId: number, kind: 'post' | 'reel') {
  return useQuery({
    queryKey: ['job', trendId, kind],
    queryFn: async (): Promise<ContentJob | null> => {
      const response = await fetch(`${API}/content/jobs?trend_id=${trendId}&kind=${kind}`, {
        cache: 'no-store',
      })
      if (response.status === 404) return null
      if (!response.ok) throw new Error(`jobs returned ${response.status}`)
      const body = await response.json()
      // The endpoint answers with the job itself, or `{}` when there is
      // none — which is falsy-ish but not null, and `body.id` is the only
      // thing that actually distinguishes them.
      return body && typeof body.id === 'number' ? (body as ContentJob) : null
    },
  })
}
