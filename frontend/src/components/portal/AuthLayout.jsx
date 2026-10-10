import { BrandMark } from "./ui";

export const HERO_IMG = "/campus.jpg";

export const AuthLayout = ({ eyebrow, title, subtitle, children, aside, testId }) => (
  <div data-testid={testId} className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
    <div className="relative hidden overflow-hidden bg-[hsl(var(--navy))] lg:block">
      <img src={HERO_IMG} alt="WeSchool campus" className="absolute inset-0 h-full w-full object-cover opacity-55" />
      <div className="absolute inset-0 bg-[hsl(var(--navy))]/60" />
      <div className="relative flex h-full flex-col justify-between p-12">
        <BrandMark light />
        <div className="max-w-md text-white">
          <div className="mb-6 h-1 w-16 bg-primary" />
          {aside}
        </div>
      </div>
    </div>
    <div className="flex flex-col px-5 py-8 sm:px-12 lg:px-16">
      <div className="lg:hidden"><BrandMark /></div>
      <div className="my-auto w-full max-w-md py-10">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-3 text-sm text-muted-foreground sm:text-base">{subtitle}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </div>
  </div>
);
