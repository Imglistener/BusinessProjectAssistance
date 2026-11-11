import {
  Bell,
  Boxes,
  Building2,
  Check,
  ChevronsUpDown,
  LayoutDashboard,
  LogOut,
  Settings,
  Sparkles,
  Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useOrg } from "../auth/OrgContext";
import { isRtl, t } from "../i18n";
import { LanguagePicker } from "./LanguagePicker";
import { Logo, LogoMark } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { setReduceMotion, useReduceMotion } from "@/hooks/use-reduce-motion";

/** Fired after notifications are read, so the sidebar count refreshes at once. */
export const NOTIFICATIONS_CHANGED = "bpa:notifications-changed";
const POLL_MS = 60_000;

function useUnreadCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api<{ unread_count: number }>("/notifications?limit=1")
        .then((r) => alive && setCount(r.unread_count))
        .catch(() => undefined);
    check();
    const timer = window.setInterval(() => document.visibilityState === "visible" && check(), POLL_MS);
    window.addEventListener(NOTIFICATIONS_CHANGED, check);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener(NOTIFICATIONS_CHANGED, check);
    };
  }, []);
  return count;
}

const initials = (first?: string, last?: string) => `${first?.[0] ?? ""}${last?.[0] ?? ""}`.toUpperCase() || "?";

function OrgSwitcher() {
  const { orgs, org, select } = useOrg();
  const navigate = useNavigate();
  const { isMobile } = useSidebar();
  if (!org) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" asChild>
            <Link to="/app">
              <OrgBadge />
              <span className="truncate text-sm font-semibold">Business Project Assistance</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }
  const multiple = (orgs?.length ?? 0) > 1;
  const button = (
    <SidebarMenuButton
      size="lg"
      className={cn(multiple && "data-[state=open]:bg-sidebar-accent")}
      asChild={!multiple}
      tooltip={org.name}
    >
      {multiple ? (
        <>
          <OrgBadge />
          <OrgText name={org.name} />
          <ChevronsUpDown className="ms-auto size-4 opacity-60" />
        </>
      ) : (
        <Link to="/app">
          <OrgBadge />
          <OrgText name={org.name} />
        </Link>
      )}
    </SidebarMenuButton>
  );
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        {multiple ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>{button}</DropdownMenuTrigger>
            <DropdownMenuContent
              className="min-w-56"
              side={isMobile ? "bottom" : isRtl() ? "left" : "right"}
              align="start"
            >
              <DropdownMenuLabel className="text-xs text-muted-foreground">{t("Organization")}</DropdownMenuLabel>
              {orgs!.map((o) => (
                <DropdownMenuItem
                  key={o.id}
                  onSelect={() => {
                    select(o.id);
                    navigate("/app");
                  }}
                >
                  <Building2 className="size-4 opacity-60" />
                  <span className="flex-1 truncate">{o.name}</span>
                  {o.id === org.id && <Check className="size-4 text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          button
        )}
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

function OrgBadge() {
  return (
    <span className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
      <LogoMark className="size-5 text-primary-foreground" />
    </span>
  );
}

function OrgText({ name }: { name: string }) {
  return (
    <span className="grid flex-1 text-start leading-tight transition-opacity duration-200 group-data-[collapsible=icon]:opacity-0">
      <span className="truncate text-sm font-semibold">{name}</span>
      <span className="truncate text-xs text-muted-foreground">Business Project Assistance</span>
    </span>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { isMobile } = useSidebar();
  const name = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim();
  const reduce = useReduceMotion();
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent" tooltip={name}>
              <Avatar className="size-8 rounded-lg">
                <AvatarFallback className="rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                  {initials(user?.first_name, user?.last_name)}
                </AvatarFallback>
              </Avatar>
              <span className="grid flex-1 text-start leading-tight transition-opacity duration-200 group-data-[collapsible=icon]:opacity-0">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
              </span>
              <ChevronsUpDown className="ms-auto size-4 opacity-60" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="min-w-56"
            side={isMobile ? "bottom" : isRtl() ? "left" : "right"}
            align="end"
          >
            <DropdownMenuLabel className="font-normal">
              <div className="grid leading-tight">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem
              checked={reduce}
              onCheckedChange={(v) => setReduceMotion(v === true)}
              onSelect={(e) => e.preventDefault()}
            >
              {t("Reduce motion")}
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/app/settings")}>
              <Settings className="size-4" />
              {t("Settings")}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                logout();
                navigate("/login", { replace: true });
              }}
            >
              <LogOut className="size-4" />
              {t("Log out")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

/**
 * Sidebar and page frame shared by every signed-in screen.
 * Screens not rebuilt with Tailwind yet pass `legacy` so the older stylesheet applies to them.
 */
export function AppShell({ children, legacy = true }: { children: ReactNode; legacy?: boolean }) {
  const { pathname } = useLocation();
  const unread = useUnreadCount();
  const rtl = isRtl();

  const items = [
    { to: "/app/assistant", label: t("Assistant"), icon: Sparkles },
    { to: "/app/inventory", label: t("Inventory"), icon: Boxes },
    { to: "/app/notifications", label: t("Notifications"), icon: Bell, badge: unread },
    { to: "/app/members", label: t("Members"), icon: Users },
    { to: "/app/settings", label: t("Settings"), icon: Settings },
  ];
  const onOther = items.some((i) => pathname.startsWith(i.to));
  // Project and trip pages belong to the dashboard section.
  const nav = [{ to: "/app", label: t("Dashboard"), icon: LayoutDashboard, active: !onOther }, ...items.map((i) => ({ ...i, active: pathname.startsWith(i.to) }))];

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon" side={rtl ? "right" : "left"}>
        <SidebarHeader>
          <OrgSwitcher />
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu aria-label={t("Main")}>
                {nav.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      isActive={item.active}
                      tooltip={{ children: item.label, side: rtl ? "left" : "right" }}
                    >
                      <Link to={item.to} aria-current={item.active ? "page" : undefined}>
                        <item.icon />
                        <span className="transition-opacity duration-200 group-data-[collapsible=icon]:opacity-0">{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {"badge" in item && typeof item.badge === "number" && item.badge > 0 && (
                      <SidebarMenuBadge
                        className="bg-primary text-primary-foreground peer-hover/menu-button:text-primary-foreground"
                        aria-label={t("{unread} unread", { unread: item.badge })}
                      >
                        {item.badge > 99 ? "99+" : item.badge}
                      </SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <UserMenu />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <SidebarTrigger className="-ms-1" aria-label={t("Toggle the menu")} />
          <Separator orientation="vertical" className="me-1 data-[orientation=vertical]:h-4" />
          <Logo compact className="text-sm md:hidden" />
          <div className="ms-auto flex items-center gap-1">
            <LanguagePicker />
            <ThemeToggle />
          </div>
        </header>
        {legacy ? (
          <div className="legacy flex-1">
            <div className="main">{children}</div>
          </div>
        ) : (
          <div className="flex-1">{children}</div>
        )}
      </SidebarInset>
    </SidebarProvider>
  );
}
