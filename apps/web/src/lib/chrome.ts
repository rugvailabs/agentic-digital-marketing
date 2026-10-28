/**
 * The two bits of chrome state that have to be right before the first
 * paint: which theme, and whether the sidebar is a rail.
 *
 * Both live as attributes on <html>, both are set by an inline script that
 * runs before the body exists, and both are read back from there by React
 * after hydration. Keeping them out of React state is the whole point —
 * a theme stored in state flashes dark-then-light on every navigation, and
 * a sidebar width stored in state is 240px for one frame on every page
 * load regardless of what the user chose.
 */

export type Theme = 'dark' | 'light'

export const THEME_KEY = 'trendforge.theme'
export const SIDEBAR_KEY = 'trendforge.sidebar'

/** Dark unless the user has said otherwise. */
export const DEFAULT_THEME: Theme = 'dark'

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Private mode. The choice holds for this tab and is forgotten after.
  }
}

/**
 * The inline script, as a string.
 *
 * Minified by hand rather than by a build step because it is injected with
 * dangerouslySetInnerHTML and has to stay readable in the page source —
 * this is the one piece of the app a developer will find by View Source
 * while wondering why the page is dark.
 *
 * Wrapped in try/catch: localStorage throws in private mode in some
 * browsers, and an exception here would run before anything else and take
 * the whole page with it.
 */
export const CHROME_SCRIPT = `try{var d=document.documentElement,t=localStorage.getItem('${THEME_KEY}');d.dataset.theme=t==='light'?'light':'dark';d.dataset.sidebar=localStorage.getItem('${SIDEBAR_KEY}')==='rail'?'rail':'full'}catch(e){document.documentElement.dataset.theme='dark';document.documentElement.dataset.sidebar='full'}`
