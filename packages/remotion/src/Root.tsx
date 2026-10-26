/**
 * The two compositions CLAUDE.md asks for: Reel 9:16 and Square 1:1.
 *
 * One component serves both: a square is the reel with less vertical room,
 * not a second layout to keep in step.
 */

import { type CalculateMetadataFunction, Composition } from 'remotion'

import { Wire } from './compositions/Wire'
import { type ReelProps, defaultProps, withDefaults } from './props'

/**
 * Geometry and length come from the props, not from the registration below.
 * The voiceover decides how long a reel is — the Python side narrates first,
 * measures, and sends the frame count — so the registered values are only
 * what the studio opens with.
 */
const metadata: CalculateMetadataFunction<ReelProps> = ({ props }) => {
  const safe = withDefaults(props)
  return {
    durationInFrames: safe.durationInFrames,
    fps: safe.fps,
    width: safe.width,
    height: safe.height,
  }
}

export function Root() {
  return (
    <>
      <Composition
        id="Reel"
        component={Wire}
        defaultProps={defaultProps}
        calculateMetadata={metadata}
        durationInFrames={defaultProps.durationInFrames}
        fps={defaultProps.fps}
        width={1080}
        height={1920}
      />
      <Composition
        id="Square"
        component={Wire}
        defaultProps={{ ...defaultProps, width: 1080, height: 1080 }}
        calculateMetadata={metadata}
        durationInFrames={defaultProps.durationInFrames}
        fps={defaultProps.fps}
        width={1080}
        height={1080}
      />
    </>
  )
}
