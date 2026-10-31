import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { StarMark, Wordmark, ZellijField } from "../components/Zellij";

/** Public page for signed-out visitors: what the product does, and a way in. */
export default function Landing() {
  const { user } = useAuth();

  return (
    <div className="landing">
      <header className="lp-hero">
        <ZellijField className="lp-hero__field" />
        <nav className="lp-nav" aria-label="Site">
          <Wordmark light />
          <div className="lp-nav__links">
            <a href="#features">What it does</a>
            <a href="#assistant">The assistant</a>
            {user ? (
              <Link className="btn btn--saffron" to="/app">
                Open your dashboard
              </Link>
            ) : (
              <>
                <Link to="/login">Log in</Link>
                <Link className="btn btn--saffron" to="/signup">
                  Create an account
                </Link>
              </>
            )}
          </div>
        </nav>

        <div className="lp-hero__body">
          <div className="lp-hero__copy">
            <h1>From a customer’s request to a planned, budgeted project.</h1>
            <p className="lp-hero__lede">
              Projects, budgets in dirhams, tasks, trips and stock in one place, with an assistant that drafts the plan
              for you to check. Built for small teams in Morocco.
            </p>
            <div className="lp-hero__actions">
              <Link className="btn btn--saffron btn--large" to={user ? "/app" : "/signup"}>
                {user ? "Open your dashboard" : "Create a free account"}
              </Link>
              {!user && (
                <Link className="lp-hero__login" to="/login">
                  I already have an account
                </Link>
              )}
            </div>
          </div>

          <HeroDemo />
        </div>
      </header>

      <main>
        <section className="lp-features" id="features" aria-labelledby="features-title">
          <div className="lp-section-head">
            <h2 id="features-title">Everything a client project needs, and nothing it doesn’t.</h2>
            <p>
              No accounting package to learn. You record what happens; the app keeps the figures straight and tells you
              what needs attention.
            </p>
          </div>

          <Feature
            title="Budgets you can trust"
            text="Record expenses as they happen, with receipts. Spending, what’s left and how far over you are are worked out the same way everywhere, and you’re told the moment a project goes over."
          >
            <div className="lp-frag lp-frag--budget" aria-hidden="true">
              <div className="lp-frag__row">
                <strong>Website redesign</strong>
                <span>48,600 of 45,000 MAD</span>
              </div>
              <div className="lp-bar">
                <span style={{ width: "100%" }} />
              </div>
              <p className="lp-frag__over">Over budget by 3,600.00 MAD</p>
            </div>
          </Feature>

          <Feature
            title="Tasks, milestones and deadlines"
            text="Assign work, set due dates and group tasks under milestones. Your dashboard lists what’s overdue and what’s due in the next two weeks, across every project."
          >
            <ul className="lp-frag lp-frag--deadlines" aria-hidden="true">
              <li>
                <span className="lp-late">6 days overdue</span>
                <span>Book internet installation</span>
              </li>
              <li>
                <span>Due tomorrow</span>
                <span>Booking form QA</span>
              </li>
              <li>
                <span>Leaves in 6 days</span>
                <span>Furniture pickup, Tangier</span>
              </li>
            </ul>
          </Feature>

          <Feature
            title="Trips with a real fuel estimate"
            text="Pick the start and finish on a map, choose the vehicle, and see what the fuel will cost: an expected figure and a likely range, using current average pump prices in Morocco."
          >
            <div className="lp-frag lp-frag--fuel" aria-hidden="true">
              <div className="lp-frag__row">
                <span>Casablanca to Tangier and back, van</span>
                <strong>734 MAD</strong>
              </div>
              <div className="lp-range">
                <span className="lp-range__dot" style={{ left: "42%" }} />
              </div>
              <div className="lp-frag__row lp-frag__muted">
                <span>581 MAD</span>
                <span>905 MAD</span>
              </div>
            </div>
          </Feature>

          <Feature
            title="Stock that adds up"
            text="Receive, issue and count what you keep in stock. A stock count shows exactly what differs from the records, and low stock is flagged before you run out."
          >
            <div className="lp-frag lp-frag--count" aria-hidden="true">
              <div className="lp-frag__row">
                <span>Office chair</span>
                <span>expected 8, counted 7</span>
                <strong className="lp-late">−1</strong>
              </div>
              <div className="lp-frag__row">
                <span>Printer paper A4</span>
                <span className="lp-chip">Low stock</span>
              </div>
            </div>
          </Feature>

          <Feature
            title="Your team, with the right access"
            text="Invite people by email as owners, project managers, contributors or viewers. Every change is recorded, so you can see who did what on each project."
          >
            <div className="lp-frag lp-frag--team" aria-hidden="true">
              <div className="lp-frag__row">
                <span>Salma Bennani</span>
                <span className="lp-chip lp-chip--quiet">Contributor</span>
              </div>
              <p className="lp-frag__muted">Salma recorded an expense: Travel, 1,850.50 MAD.</p>
            </div>
          </Feature>

          <Feature
            title="Reports to send"
            text="A one-page project report with spending by category and month, ready to print or save as PDF, and CSV exports of expenses and tasks for Excel."
          >
            <div className="lp-frag lp-frag--report" aria-hidden="true">
              {[
                ["Design", 38],
                ["Services", 30],
                ["Marketing", 16],
                ["Software", 15],
              ].map(([name, pct]) => (
                <div className="lp-frag__bar-row" key={name}>
                  <span>{name}</span>
                  <span className="lp-mini-bar">
                    <span style={{ width: `${pct}%` }} />
                  </span>
                  <span>{pct}%</span>
                </div>
              ))}
            </div>
          </Feature>
        </section>

        <section className="lp-assistant" id="assistant" aria-labelledby="assistant-title">
          <div className="lp-assistant__mark">
            <StarMark size={72} />
          </div>
          <div>
            <h2 id="assistant-title">An assistant that shows its working.</h2>
            <p>
              Ask about your projects in plain language, in English or French. It looks up your figures and calculates
              with the same rules as the rest of the app, rather than guessing.
            </p>
            <ul className="lp-promises">
              <li>
                <strong>It drafts, you decide.</strong> A project plan, a status update or a fuel estimate is a draft
                until you confirm it. It can’t change your records on its own.
              </li>
              <li>
                <strong>It says what it assumed.</strong> Estimates come with their assumptions, and it tells you when
                data is missing instead of inventing a number.
              </li>
              <li>
                <strong>It only sees your organization.</strong> Every lookup checks what you’re allowed to see.
              </li>
            </ul>
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="cta-title">
          <ZellijField className="lp-cta__field" />
          <div className="lp-cta__body">
            <h2 id="cta-title">Set up your first project in a few minutes.</h2>
            <p>Create an account, name your organization and invite your team when you’re ready.</p>
            <Link className="btn btn--saffron btn--large" to={user ? "/app" : "/signup"}>
              {user ? "Open your dashboard" : "Create a free account"}
            </Link>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <Wordmark />
        <p>Amounts in MAD by default. Fuel prices: averages from prix-gasoil-maroc.teraedge.ma.</p>
        <Link to="/login">Log in</Link>
      </footer>
    </div>
  );
}

function Feature({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <article className="lp-feature">
      <div className="lp-feature__text">
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
      <div className="lp-feature__frag">{children}</div>
    </article>
  );
}

/** The product's signature moment, in miniature: a customer's request becomes a drafted project. */
function HeroDemo() {
  const tasks = ["Shortlist hotels in Ifrane", "Book the coach from Casablanca", "Plan two days of workshops"];
  return (
    <div className="lp-demo" aria-label="Example: the assistant drafts a project from a customer's request">
      <p className="lp-demo__ask">
        Atlas Bank wants a 3-day team retreat in Ifrane for 25 people next March. Budget about 80,000 MAD.
      </p>
      <div className="lp-demo__draft">
        <div className="lp-demo__head">
          <span className="lp-chip">Draft project</span>
          <span className="lp-demo__budget">80,000.00 MAD</span>
        </div>
        <p className="lp-demo__name">Atlas Bank team retreat, Ifrane</p>
        <p className="lp-demo__dates">15 to 17 March 2027</p>
        <ul className="lp-demo__tasks">
          {tasks.map((t, i) => (
            <li key={t} style={{ animationDelay: `${0.9 + i * 0.25}s` }}>
              {t}
            </li>
          ))}
        </ul>
        <span className="lp-demo__button">Create project</span>
      </div>
    </div>
  );
}
