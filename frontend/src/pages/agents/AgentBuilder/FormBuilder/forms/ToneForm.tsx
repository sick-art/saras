import { TextAreaField } from "../fields/TextAreaField"

interface Props {
  value: string
  onChange: (v: string) => void
}

export function ToneForm({ value, onChange }: Props) {
  return (
    <TextAreaField
      label="Default tone"
      hint="Default communication style for the agent's responses. Plain English."
      value={value}
      onChange={onChange}
      placeholder="Friendly, professional, and concise. Empathise with the customer's situation. Avoid jargon."
      rows={5}
    />
  )
}
