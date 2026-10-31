import {
  ArrowRight,
  Boxes,
  CalendarClock,
  FileBarChart,
  Fuel,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  Users,
  Wallet,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LanguagePicker } from "../components/LanguagePicker";
import { Logo } from "../components/Logo";
import { ThemeToggle } from "../components/ThemeToggle";
import BlurText from "../components/effects/BlurText";
import DotGrid from "../components/effects/DotGrid";
import { Marquee } from "../components/effects/Marquee";
import SpotlightCard from "../components/effects/SpotlightCard";
import { TimelineAnimation } from "../components/effects/TimelineAnimation";
import { useIsDark } from "../hooks/use-dark";
import { isRtl, t } from "../i18n";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Public page for signed-out visitors: what the product does, and a way in. */
export default function Landing() {
  const { user } = useAuth();
  const primaryTo = user ? "/app" : "/signup";
  const primaryLabel = user ? t("Open your dashboard") : t("Create a free account");

  return (
    <div className="min-h-svh bg-background text-foreground">
      <Header signedIn={!!user} />
      <main>
        <Hero primaryTo={primaryTo} primaryLabel={primaryLabel} signedIn={!!user} />
        <Features />
        <HowItWorks />
        <AssistantSection />
        <Faq />
        <FinalCta primaryTo={primaryTo} primaryLabel={primaryLabel} />
      </main>
      <Footer />
    </div>
  );
}

function Header({ signedIn }: { signedIn: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-transparent bg-background/70 backdrop-blur-md supports-[backdrop-filter]:bg-background/55">
      <nav aria-label={t("Site")} className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 md:px-6">
        <Link to="/" className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Logo compact className="hidden sm:inline-flex" />
          <Logo className="sm:hidden" />
        </Link>
        <div className="hidden items-center gap-1 text-sm text-muted-foreground md:flex">
          <a href="#features" className="rounded-md px-3 py-2 transition-colors hover:text-foreground">
            {t("What it does")}
          </a>
          <a href="#how" className="rounded-md px-3 py-2 transition-colors hover:text-foreground">
            {t("How it works")}
          </a>
          <a href="#assistant" className="rounded-md px-3 py-2 transition-colors hover:text-foreground">
            {t("The assistant")}
          </a>
          <a href="#faq" className="rounded-md px-3 py-2 transition-colors hover:text-foreground">
            {t("Questions")}
          </a>
        </div>
        <div className="ms-auto flex items-center gap-1">
          <LanguagePicker iconOnly className="sm:hidden" />
          <LanguagePicker className="hidden sm:inline-flex" />
          <ThemeToggle />
          {signedIn ? (
            <Button asChild size="sm" className="ms-1">
              <Link to="/app">{t("Open your dashboard")}</Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                <Link to="/login">{t("Log in")}</Link>
              </Button>
              <Button asChild size="sm" className="ms-1">
                <Link to="/signup">{t("Create an account")}</Link>
              </Button>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}

function Hero({ primaryTo, primaryLabel, signedIn }: { primaryTo: string; primaryLabel: string; signedIn: boolean }) {
  const dark = useIsDark();
  const reduce = useReducedMotion();
  return (
    <section className="relative isolate overflow-hidden">
      <div aria-hidden="true" className="absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_30%,#000_40%,transparent_100%)]">
        <DotGrid
          dotSize={3}
          gap={22}
          baseColor={dark ? "#2a2a33" : "#dcdce6"}
          activeColor={dark ? "#7c86ff" : "#4b4fe0"}
          proximity={130}
          shockRadius={220}
          shockStrength={4}
          intro={!reduce}
          mouseInteraction={!reduce}
          paused={!!reduce}
          className="h-full w-full"
        />
      </div>
      <div
        aria-hidden="true"
        className="absolute start-1/2 top-24 -z-10 size-[36rem] -translate-x-1/2 rounded-full bg-primary/15 blur-[120px] rtl:translate-x-1/2"
      />

      <div className="mx-auto grid max-w-6xl items-center gap-14 px-4 pb-20 pt-16 md:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:pb-28 lg:pt-24">
        <div className="grid justify-items-start gap-7">
          <motion.a
            href="#assistant"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="group inline-flex items-center gap-2 rounded-full border bg-background/70 py-1 pe-3 ps-1 text-xs text-muted-foreground shadow-xs backdrop-blur transition-colors hover:text-foreground"
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 font-medium text-primary-foreground">
              <Sparkles className="size-3" />
              {t("New")}
            </span>
            {t("The assistant drafts projects from a customer's request")}
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5" />
          </motion.a>

          <h1 className="text-4xl font-semibold leading-[1.05] tracking-tight text-balance sm:text-5xl lg:text-6xl">
            {reduce ? (
              t("From a customer’s request to a planned, budgeted project.")
            ) : (
              <BlurText
                text={t("From a customer’s request to a planned, budgeted project.")}
                animateBy="words"
                direction="bottom"
                delay={70}
                trigger="load"
                className="inline"
              />
            )}
          </h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            className="max-w-xl text-lg text-pretty text-muted-foreground"
          >
            {t(
              "Projects, budgets in dirhams, tasks, trips and stock in one place, with an assistant that drafts the plan for you to check. Built for small teams in Morocco.",
            )}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.7 }}
            className="flex flex-wrap items-center gap-3"
          >
            <Button asChild size="lg" className="h-11 px-6 shadow-lg shadow-primary/25">
              <Link to={primaryTo}>
                {primaryLabel}
                <ArrowRight className="size-4 rtl:rotate-180" />
              </Link>
            </Button>
            {!signedIn && (
              <Button asChild size="lg" variant="ghost" className="h-11">
                <Link to="/login">{t("I already have an account")}</Link>
              </Button>
            )}
          </motion.div>
        </div>

        <HeroDemo />
      </div>
    </section>
  );
}

/** The product's signature moment, in miniature: a customer's request becomes a drafted project. */
function HeroDemo() {
  const tasks = [t("Shortlist hotels in Ifrane"), t("Book the coach from Casablanca"), t("Plan two days of workshops")];
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.6, delay: 0.3, ease: [0.2, 0.7, 0.2, 1] }}
      aria-label={t("Example: the assistant drafts a project from a customer's request")}
      role="img"
      className="relative"
    >
      <div className="rounded-2xl border bg-card/80 p-3 shadow-2xl shadow-primary/10 backdrop-blur-sm">
        <div className="flex items-center gap-1.5 px-2 pb-3 pt-1" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
          <span className="size-2.5 rounded-full bg-muted-foreground/25" />
        </div>
        <div className="grid gap-3 rounded-xl border bg-background p-4">
          <motion.p
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.7 }}
            className="ms-auto max-w-[85%] rounded-2xl rounded-ee-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground"
          >
            {t("Atlas Bank wants a 3-day team retreat in Ifrane for 25 people next March. Budget about 80,000 MAD.")}
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 1.2 }}
            className="grid gap-3 rounded-xl border bg-card p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <Badge variant="secondary" className="gap-1 bg-primary/10 text-primary">
                <Sparkles className="size-3" />
                {t("Draft project")}
              </Badge>
              <span className="tabular text-sm font-semibold">{t("80,000.00 MAD")}</span>
            </div>
            <div>
              <p className="font-semibold">{t("Atlas Bank team retreat, Ifrane")}</p>
              <p className="text-xs text-muted-foreground">{t("15 to 17 March 2027")}</p>
            </div>
            <ul className="grid gap-1.5">
              {tasks.map((task, i) => (
                <motion.li
                  key={task}
                  initial={{ opacity: 0, x: isRtl() ? 8 : -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: 1.6 + i * 0.25 }}
                  className="flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-2 text-sm"
                >
                  <span className="size-3.5 shrink-0 rounded-[4px] border-2 border-primary bg-primary/15" />
                  {task}
                </motion.li>
              ))}
            </ul>
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 2.5 }}
              className="justify-self-end rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
            >
              {t("Create project")}
            </motion.span>
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}

function SectionHead({ id, title, text }: { id: string; title: string; text?: string }) {
  return (
    <div className="mx-auto mb-12 grid max-w-2xl gap-3 text-center">
      <h2 id={id} className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">
        {title}
      </h2>
      {text && <p className="text-pretty text-muted-foreground">{text}</p>}
    </div>
  );
}

function Feature({
  icon,
  title,
  text,
  className,
  children,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  className?: string;
  children?: ReactNode;
}) {
  const dark = useIsDark();
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
      className={cn("h-full", className)}
    >
      <SpotlightCard
        theme={dark ? "dark" : "light"}
        spotlightColor={dark ? "rgba(124, 134, 255, 0.22)" : "rgba(75, 79, 224, 0.12)"}
        className="flex h-full flex-col gap-5 rounded-2xl p-6"
      >
        <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">{icon}</span>
        <div className="grid gap-2">
          <h3 className="text-lg font-semibold">{title}</h3>
          <p className="text-sm leading-relaxed text-muted-foreground">{text}</p>
        </div>
        {children && <div className="mt-auto">{children}</div>}
      </SpotlightCard>
    </motion.div>
  );
}

function Features() {
  return (
    <section id="features" aria-labelledby="features-title" className="scroll-mt-20 px-4 py-24 md:px-6">
      <div className="mx-auto max-w-6xl">
        <SectionHead
          id="features-title"
          title={t("Everything a client project needs, and nothing it doesn’t.")}
          text={t(
            "No accounting package to learn. You record what happens; the app keeps the figures straight and tells you what needs attention.",
          )}
        />
        <div className="grid gap-4 md:grid-cols-6">
          <Feature
            className="md:col-span-4"
            icon={<Wallet className="size-5" />}
            title={t("Budgets you can trust")}
            text={t(
              "Record expenses as they happen, with receipts. Spending, what’s left and how far over you are are worked out the same way everywhere, and you’re told the moment a project goes over.",
            )}
          >
            <div className="grid gap-2 rounded-xl border bg-background/60 p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{t("Website redesign")}</span>
                <span className="tabular text-muted-foreground">{t("48,600 of 45,000 MAD")}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <motion.div
                  className="h-full rounded-full bg-destructive"
                  initial={{ width: 0 }}
                  whileInView={{ width: "100%" }}
                  viewport={{ once: true }}
                  transition={{ duration: 1, ease: [0.2, 0.7, 0.2, 1] }}
                />
              </div>
              <p className="tabular text-xs font-medium text-destructive">{t("Over budget by 3,600.00 MAD")}</p>
            </div>
          </Feature>
          <Feature
            className="md:col-span-2"
            icon={<CalendarClock className="size-5" />}
            title={t("Tasks, milestones and deadlines")}
            text={t(
              "Assign work, set due dates and group tasks under milestones. Your dashboard lists what’s overdue and what’s due in the next two weeks, across every project.",
            )}
          />
          <Feature
            className="md:col-span-2"
            icon={<Fuel className="size-5" />}
            title={t("Trips with a real fuel estimate")}
            text={t(
              "Pick the start and finish on a map, choose the vehicle, and see what the fuel will cost: an expected figure and a likely range, using current average pump prices in Morocco.",
            )}
          >
            <div className="grid gap-2 rounded-xl border bg-background/60 p-4">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="text-muted-foreground">{t("Casablanca to Tangier and back, van")}</span>
                <span className="tabular font-semibold">{t("734 MAD")}</span>
              </div>
              <div className="relative h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-red-500 rtl:bg-gradient-to-l">
                <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground start-[42%] rtl:translate-x-1/2" />
              </div>
              <div className="tabular flex justify-between text-[11px] text-muted-foreground">
                <span>{t("581 MAD")}</span>
                <span>{t("905 MAD")}</span>
              </div>
            </div>
          </Feature>
          <Feature
            className="md:col-span-2"
            icon={<Boxes className="size-5" />}
            title={t("Stock that adds up")}
            text={t(
              "Receive, issue and count what you keep in stock. A stock count shows exactly what differs from the records, and low stock is flagged before you run out.",
            )}
          />
          <Feature
            className="md:col-span-2"
            icon={<Users className="size-5" />}
            title={t("Your team, with the right access")}
            text={t(
              "Invite people by email as owners, project managers, contributors or viewers. Every change is recorded, so you can see who did what on each project.",
            )}
          />
          <Feature
            className="md:col-span-6"
            icon={<FileBarChart className="size-5" />}
            title={t("Reports to send")}
            text={t(
              "A one-page project report with spending by category and month, ready to print or save as PDF, and CSV exports of expenses and tasks for Excel.",
            )}
          >
            <div className="grid gap-2 sm:grid-cols-4">
              {(
                [
                  [t("Design"), 38],
                  [t("Services"), 30],
                  [t("Marketing"), 16],
                  [t("Software"), 15],
                ] as const
              ).map(([name, pct], i) => (
                <div key={name} className="grid gap-1.5 rounded-xl border bg-background/60 p-3">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{name}</span>
                    <span className="tabular font-medium">{pct}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <motion.div
                      className="h-full rounded-full bg-primary"
                      initial={{ width: 0 }}
                      whileInView={{ width: `${pct * 2.2}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.8, delay: i * 0.1 }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Feature>
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const steps = [
    {
      title: t("Create your organization"),
      text: t("Name it, choose your currency and invite your team by email when you're ready."),
    },
    {
      title: t("Describe the work"),
      text: t(
        "Tell the assistant what the customer wants. It drafts the project, budget, milestones and tasks for you to check and adjust.",
      ),
    },
    {
      title: t("Track it day to day"),
      text: t("Record expenses and tasks as they happen. The dashboard warns you before budgets and deadlines slip."),
    },
  ];
  return (
    <section id="how" aria-labelledby="how-title" className="scroll-mt-20 border-y bg-muted/30 px-4 py-24 md:px-6">
      <div className="mx-auto max-w-6xl" ref={ref}>
        <SectionHead
          id="how-title"
          title={t("How it works")}
          text={t("Three steps from your first login to a project you can trust.")}
        />
        <div className="relative">
          <div aria-hidden="true" className="absolute inset-x-[16%] top-6 hidden h-px bg-border md:block" />
          <ol className="relative grid gap-6 md:grid-cols-3">
          {steps.map((s, i) => (
            <TimelineAnimation
              key={s.title}
              as="li"
              animationNum={i}
              timelineRef={ref}
              customVariants={{
                visible: (n: number) => ({
                  opacity: 1,
                  y: 0,
                  filter: "blur(0px)",
                  transition: { delay: n * 0.25, duration: 0.5 },
                }),
                hidden: { opacity: 0, y: 12, filter: "blur(8px)" },
              }}
              className="relative grid justify-items-center gap-3 text-center"
            >
              <span className="tabular relative flex size-12 items-center justify-center rounded-full border bg-background text-sm font-semibold shadow-sm">
                {i + 1}
              </span>
              <h3 className="font-semibold">{s.title}</h3>
              <p className="max-w-xs text-sm text-muted-foreground">{s.text}</p>
            </TimelineAnimation>
          ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function AssistantSection() {
  const questions = [
    t("Which projects need attention right now?"),
    t("What would it cost in fuel to drive a van from Casablanca to Marrakech and back?"),
    t("At the current spend rate, how long will the budget last?"),
    t("What's running low in stock?"),
    t("Draft a short status update I can share."),
    t("What's the VAT on 12,500 MAD, and the total including VAT?"),
  ];
  const promises = [
    {
      icon: <Sparkles className="size-4" />,
      title: t("It drafts, you decide."),
      text: t("A project plan, a status update or a fuel estimate is a draft until you confirm it. It can’t change your records on its own."),
    },
    {
      icon: <MessageSquareText className="size-4" />,
      title: t("It says what it assumed."),
      text: t("Estimates come with their assumptions, and it tells you when data is missing instead of inventing a number."),
    },
    {
      icon: <ShieldCheck className="size-4" />,
      title: t("It only sees your organization."),
      text: t("Every lookup checks what you’re allowed to see."),
    },
  ];
  return (
    <section id="assistant" aria-labelledby="assistant-title" className="scroll-mt-20 overflow-hidden py-24">
      <div className="mx-auto max-w-6xl px-4 md:px-6">
        <SectionHead
          id="assistant-title"
          title={t("An assistant that shows its working.")}
          text={t(
            "Ask about your projects in plain language, in English, French or Arabic. It looks up your figures and calculates with the same rules as the rest of the app, rather than guessing.",
          )}
        />
      </div>
      <div className="relative [mask-image:linear-gradient(to_right,transparent,#000_12%,#000_88%,transparent)]" dir="ltr">
        <Marquee pauseOnHover repeat={3} className="[--duration:55s]">
          {questions.map((q) => (
            <span
              key={q}
              dir={isRtl() ? "rtl" : "ltr"}
              className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border bg-card px-4 py-2 text-sm shadow-xs"
            >
              <MessageSquareText className="size-4 text-primary" />
              {q}
            </span>
          ))}
        </Marquee>
        <Marquee pauseOnHover reverse repeat={3} className="[--duration:65s]">
          {[...questions].reverse().map((q) => (
            <span
              key={q}
              dir={isRtl() ? "rtl" : "ltr"}
              className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border bg-card px-4 py-2 text-sm text-muted-foreground shadow-xs"
            >
              {q}
            </span>
          ))}
        </Marquee>
      </div>
      <div className="mx-auto mt-14 grid max-w-6xl gap-4 px-4 md:grid-cols-3 md:px-6">
        {promises.map((p, i) => (
          <motion.div
            key={p.title}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: i * 0.1 }}
            className="grid gap-2 rounded-2xl border p-6"
          >
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">{p.icon}</span>
            <h3 className="font-semibold">{p.title}</h3>
            <p className="text-sm text-muted-foreground">{p.text}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function Faq() {
  const items = [
    {
      q: t("Which languages does it speak?"),
      a: t(
        "The app is available in English, French and Arabic, and the assistant answers in the language you write in. Password-reset emails and notifications follow the language you pick.",
      ),
    },
    {
      q: t("Can the assistant change my data?"),
      a: t(
        "No. It only reads what you're allowed to see. When it drafts a project, nothing is created until you review the draft and select Create project.",
      ),
    },
    {
      q: t("Where do the fuel prices come from?"),
      a: t(
        "From daily averages published by prix-gasoil-maroc.teraedge.ma, or from prices your team enters for each city. Estimates always show the price date they used.",
      ),
    },
    {
      q: t("Can I use a currency other than dirhams?"),
      a: t("Yes. Amounts are in MAD by default, and each project can use its own currency."),
    },
    {
      q: t("Can I get my data out?"),
      a: t("Every project has a printable report, and expenses and tasks export to CSV for Excel."),
    },
  ];
  return (
    <section id="faq" aria-labelledby="faq-title" className="scroll-mt-20 border-t px-4 py-24 md:px-6">
      <div className="mx-auto max-w-3xl">
        <SectionHead id="faq-title" title={t("Questions, answered")} />
        <Accordion type="single" collapsible className="w-full">
          {items.map((item, i) => (
            <AccordionItem key={item.q} value={`q${i}`}>
              <AccordionTrigger className="text-start text-base">{item.q}</AccordionTrigger>
              <AccordionContent className="text-muted-foreground">{item.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}

function FinalCta({ primaryTo, primaryLabel }: { primaryTo: string; primaryLabel: string }) {
  return (
    <section aria-labelledby="cta-title" className="px-4 pb-24 md:px-6">
      <div className="relative mx-auto grid max-w-6xl justify-items-center gap-5 overflow-hidden rounded-3xl bg-primary px-6 py-16 text-center text-primary-foreground">
        <div aria-hidden="true" className="absolute -top-32 start-1/2 size-96 -translate-x-1/2 rounded-full bg-white/15 blur-3xl rtl:translate-x-1/2" />
        <h2 id="cta-title" className="relative max-w-2xl text-3xl font-semibold tracking-tight text-balance md:text-4xl">
          {t("Set up your first project in a few minutes.")}
        </h2>
        <p className="relative max-w-xl text-primary-foreground/80">
          {t("Create an account, name your organization and invite your team when you’re ready.")}
        </p>
        <Button asChild size="lg" variant="secondary" className="relative mt-2 h-11 px-6">
          <Link to={primaryTo}>
            {primaryLabel}
            <ArrowRight className="size-4 rtl:rotate-180" />
          </Link>
        </Button>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted-foreground md:px-6">
        <Logo compact className="text-foreground" />
        <p>{t("Amounts in MAD by default. Fuel prices: averages from prix-gasoil-maroc.teraedge.ma.")}</p>
        <Link to="/login" className="font-medium text-foreground hover:underline">
          {t("Log in")}
        </Link>
      </div>
    </footer>
  );
}
