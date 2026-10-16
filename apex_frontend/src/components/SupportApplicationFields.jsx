export default function SupportApplicationFields({ fields = [], values = {}, onChange }) {
  return fields.map((field) => {
    const value = values[field.key] ?? ''
    const common = {
      required: field.required !== false,
      maxLength: field.max_length || 500,
      value,
      onChange: (event) => onChange(field.key, event.target.value),
    }

    return <label key={field.key}>
      {field.label}
      {field.type === 'textarea'
        ? <textarea {...common} rows={4} />
        : field.type === 'select'
          ? <select {...common}>
            <option value="">Choose an option</option>
            {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
          : <input
            {...common}
            type={['number', 'date'].includes(field.type) ? field.type : 'text'}
            step={field.type === 'number' ? 'any' : undefined}
          />}
    </label>
  })
}
