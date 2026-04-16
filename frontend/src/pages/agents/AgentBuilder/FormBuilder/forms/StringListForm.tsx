import { StringListField } from "../fields/StringListField"

interface Props {
  label: string
  hint?: string
  placeholder: string
  addLabel?: string
  value: string[]
  onChange: (v: string[]) => void
}

/** Generic single-list editor used for global_rules and out_of_scope. */
export function StringListForm({
  label, hint, placeholder, addLabel, value, onChange,
}: Props) {
  return (
    <StringListField
      label={label}
      hint={hint}
      placeholder={placeholder}
      addLabel={addLabel}
      items={value}
      onChange={onChange}
    />
  )
}
