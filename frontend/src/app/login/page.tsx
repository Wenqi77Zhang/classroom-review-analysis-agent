import LoginForm from "@/components/LoginForm";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const demoEnabled = Boolean(process.env.DEMO_ACCOUNT_PASSWORD?.trim());
  return <LoginForm demoEnabled={demoEnabled} />;
}
