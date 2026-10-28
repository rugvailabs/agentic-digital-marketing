import { redirect } from 'next/navigation'

/**
 * The dashboard lives here. Until it exists, this is the board.
 *
 * A redirect rather than a placeholder: an invented dashboard with made-up
 * numbers would be a worse thing to leave in the tree for one commit than
 * a route that honestly sends you to the page that does work.
 */
export default function HomePage() {
  redirect('/board')
}
