import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LanguagePicker } from "../components/LanguagePicker";
import { StarMark, Wordmark, ZellijField } from "../components/Zellij";
import { t } from "../i18n";

/** Public page for signed-out visitors: what the product does, and a way in. */
export default function Landing() {
  const { user } = useAuth();

  return (
    <div className="landing">
      <header className="lp-hero">
        <ZellijField className="lp-hero__field" />
        <nav className="lp-nav" aria-label={t("Site")}>
          <Wordmark light />
          <div className="lp-nav__links">
            <LanguagePicker className="lang-picker--light" />
            <a href="#features">{t("What it does")}</a>
            <a href="#assistant">{t("The assistant")}</a>
            {user ? (
              <Link className="btn btn--saffron" to="/app">
                {t("Open your dashboard")}
              </Link>
            ) : (
              <>
                <Link to="/login">{t("Log in")}</Link>
                <Link className="btn btn--saffron" to="/signup">
                  {t("Create an account")}
                </Link>
              </>
            )}
          </div>
        </nav>

        <div className="lp-hero__body">
          <div className="lp-hero__copy">
            <h1>{t("From a customer’s request to a planned, budgeted project.")}</h1>
            <p className="lp-hero__lede">
              {t("Projects, budgets in dirhams, tasks, trips and stock in one place, with an assistant that drafts the plan for you to check. Built for small teams in Morocco.")}
            </p>
            <div className="lp-hero__actions">
              <Link className="btn btn--saffron btn--large" to={user ? "/app" : "/signup"}>
                {user ? t("Open your dashboard") : t("Create a free account")}
              </Link>
              {!user && (
                <Link className="lp-hero__login" to="/login">
                  {t("I already have an account")}
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
            <h2 id="features-title">{t("Everything a client project needs, and nothing it doesn’t.")}</h2>
            <p>
              {t("No accounting package to learn. You record what happens; the app keeps the figures straight and tells you what needs attention.")}
            </p>
          </div>

          <Feature
            title={t("Budgets you can trust")}
            text={t("Record expenses as they happen, with receipts. Spending, what’s left and how far over you are are worked out the same way everywhere, and you’re told the moment a project goes over.")}
          >
            <div className="lp-frag lp-frag--budget" aria-hidden="true">
              <div className="lp-frag__row">
                <strong>{t("Website redesign")}</strong>
                <span>{t("48,600 of 45,000 MAD")}</span>
              </div>
              <div className="lp-bar">
                <span style={{ width: "100%" }} />
              </div>
              <p className="lp-frag__over">{t("Over budget by 3,600.00 MAD")}</p>
            </div>
          </Feature>

          <Feature
            title={t("Tasks, milestones and deadlines")}
            text={t("Assign work, set due dates and group tasks under milestones. Your dashboard lists what’s overdue and what’s due in the next two weeks, across every project.")}
          >
            <ul className="lp-frag lp-frag--deadlines" aria-hidden="true">
              <li>
                <span className="lp-late">{t("6 days overdue")}</span>
                <span>{t("Book internet installation")}</span>
              </li>
              <li>
                <span>{t("Due tomorrow")}</span>
                <span>{t("Booking form QA")}</span>
              </li>
              <li>
                <span>{t("Leaves in 6 days")}</span>
                <span>{t("Furniture pickup, Tangier")}</span>
              </li>
            </ul>
          </Feature>

          <Feature
            title={t("Trips with a real fuel estimate")}
            text={t("Pick the start and finish on a map, choose the vehicle, and see what the fuel will cost: an expected figure and a likely range, using current average pump prices in Morocco.")}
          >
            <div className="lp-frag lp-frag--fuel" aria-hidden="true">
              <div className="lp-frag__row">
                <span>{t("Casablanca to Tangier and back, van")}</span>
                <strong>{t("734 MAD")}</strong>
              </div>
              <div className="lp-range">
                <span className="lp-range__dot" style={{ left: "42%" }} />
              </div>
              <div className="lp-frag__row lp-frag__muted">
                <span>{t("581 MAD")}</span>
                <span>{t("905 MAD")}</span>
              </div>
            </div>
          </Feature>

          <Feature
            title={t("Stock that adds up")}
            text={t("Receive, issue and count what you keep in stock. A stock count shows exactly what differs from the records, and low stock is flagged before you run out.")}
          >
            <div className="lp-frag lp-frag--count" aria-hidden="true">
              <div className="lp-frag__row">
                <span>{t("Office chair")}</span>
                <span>{t("expected 8, counted 7")}</span>
                <strong className="lp-late">−1</strong>
              </div>
              <div className="lp-frag__row">
                <span>{t("Printer paper A4")}</span>
                <span className="lp-chip">{t("Low stock")}</span>
              </div>
            </div>
          </Feature>

          <Feature
            title={t("Your team, with the right access")}
            text={t("Invite people by email as owners, project managers, contributors or viewers. Every change is recorded, so you can see who did what on each project.")}
          >
            <div className="lp-frag lp-frag--team" aria-hidden="true">
              <div className="lp-frag__row">
                <span>{t("Salma Bennani")}</span>
                <span className="lp-chip lp-chip--quiet">{t("Contributor")}</span>
              </div>
              <p className="lp-frag__muted">{t("Salma recorded an expense: Travel, 1,850.50 MAD.")}</p>
            </div>
          </Feature>

          <Feature
            title={t("Reports to send")}
            text={t("A one-page project report with spending by category and month, ready to print or save as PDF, and CSV exports of expenses and tasks for Excel.")}
          >
            <div className="lp-frag lp-frag--report" aria-hidden="true">
              {[
                [t("Design"), 38],
                [t("Services"), 30],
                [t("Marketing"), 16],
                [t("Software"), 15],
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
            <h2 id="assistant-title">{t("An assistant that shows its working.")}</h2>
            <p>
              {t("Ask about your projects in plain language, in English or French. It looks up your figures and calculates with the same rules as the rest of the app, rather than guessing.")}
            </p>
            <ul className="lp-promises">
              <li>
                <strong>{t("It drafts, you decide.")}</strong> {" "}{t("A project plan, a status update or a fuel estimate is a draft until you confirm it. It can’t change your records on its own.")}</li>
              <li>
                <strong>{t("It says what it assumed.")}</strong> {" "}{t("Estimates come with their assumptions, and it tells you when data is missing instead of inventing a number.")}</li>
              <li>
                <strong>{t("It only sees your organization.")}</strong> {" "}{t("Every lookup checks what you’re allowed to see.")}</li>
            </ul>
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="cta-title">
          <ZellijField className="lp-cta__field" />
          <div className="lp-cta__body">
            <h2 id="cta-title">{t("Set up your first project in a few minutes.")}</h2>
            <p>{t("Create an account, name your organization and invite your team when you’re ready.")}</p>
            <Link className="btn btn--saffron btn--large" to={user ? "/app" : "/signup"}>
              {user ? t("Open your dashboard") : t("Create a free account")}
            </Link>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <Wordmark />
        <p>{t("Amounts in MAD by default. Fuel prices: averages from prix-gasoil-maroc.teraedge.ma.")}</p>
        <Link to="/login">{t("Log in")}</Link>
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
  const tasks = [t("Shortlist hotels in Ifrane"), t("Book the coach from Casablanca"), t("Plan two days of workshops")];
  return (
    <div className="lp-demo" aria-label={t("Example: the assistant drafts a project from a customer's request")}>
      <p className="lp-demo__ask">
        {t("Atlas Bank wants a 3-day team retreat in Ifrane for 25 people next March. Budget about 80,000 MAD.")}
      </p>
      <div className="lp-demo__draft">
        <div className="lp-demo__head">
          <span className="lp-chip">{t("Draft project")}</span>
          <span className="lp-demo__budget">{t("80,000.00 MAD")}</span>
        </div>
        <p className="lp-demo__name">{t("Atlas Bank team retreat, Ifrane")}</p>
        <p className="lp-demo__dates">{t("15 to 17 March 2027")}</p>
        <ul className="lp-demo__tasks">
          {tasks.map((x, i) => (
            <li key={x} style={{ animationDelay: `${0.9 + i * 0.25}s` }}>
              {x}
            </li>
          ))}
        </ul>
        <span className="lp-demo__button">{t("Create project")}</span>
      </div>
    </div>
  );
}
