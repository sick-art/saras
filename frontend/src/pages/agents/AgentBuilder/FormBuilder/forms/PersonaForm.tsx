import { TextAreaField } from "../fields/TextAreaField"

interface Props {
  value: string
  onChange: (v: string) => void
}

export function PersonaForm({ value, onChange }: Props) {
  return (
    <TextAreaField
      label="Persona"
      hint="Who is this agent? Write as if briefing a new employee on day one — role, tenure, attitude, background knowledge."
      value={value}
      onChange={onChange}
      placeholder="You are Mara, a friendly customer support specialist with 5 years of experience helping customers with orders, returns, and billing inquiries…"
      rows={8}
    />
  )
}
