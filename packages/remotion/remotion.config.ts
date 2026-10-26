/**
 * Studio and CLI defaults. The renderer service sets its own options in
 * server/index.ts; this file only affects `remotion studio` and `remotion
 * render` run by hand.
 */

import { Config } from '@remotion/cli/config'

Config.setVideoImageFormat('jpeg')
Config.setPixelFormat('yuv420p')
// H.264 high profile plays everywhere a reel goes; the default is fine but
// being explicit means an upgrade cannot silently change what we ship.
Config.setCodec('h264')
Config.overrideWebpackConfig((config) => config)
