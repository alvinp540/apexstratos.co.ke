import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { register as registerApi } from '../../api/authAPI'
import { email, required, passwordStrength } from '../../utils/validators'

export default function RegisterForm() {
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm()
  const navigate = useNavigate()
  const password = watch('password')

  const onSubmit = async (values) => {
    try {
      await registerApi({ ...values, password2: values.confirm_password })
      toast.success('Registration successful! Check your email.')
      navigate('/login')
    } catch (err) {
      const data = err.response?.data
      const msg = typeof data === 'object' ? Object.values(data).flat().join(' ') : 'Registration failed.'
      toast.error(msg)
    }
  }

  const labelStyle = { display: 'block', marginBottom: '0.45rem', color: '#e2e8f0', fontWeight: 600 }
  const inputStyle = {
    width: '100%',
    padding: '0.75rem 0.9rem',
    borderRadius: '0.8rem',
    border: '1px solid rgba(148,163,184,0.22)',
    background: 'rgba(15, 23, 42, 0.9)',
    color: '#f8fafc',
    fontSize: '0.95rem',
    boxSizing: 'border-box',
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div>
        <label style={labelStyle}>Username</label>
        <input
          {...register('username', { validate: required, minLength: { value: 3, message: 'Min 3 chars' } })}
          style={inputStyle}
        />
        {errors.username && <span style={{ color: '#fca5a5', fontSize: '0.8rem', display: 'block', marginTop: '0.35rem' }}>{errors.username.message}</span>}
      </div>

      <div>
        <label style={labelStyle}>Email</label>
        <input type="email" {...register('email', { validate: email })} style={inputStyle} />
        {errors.email && <span style={{ color: '#fca5a5', fontSize: '0.8rem', display: 'block', marginTop: '0.35rem' }}>{errors.email.message}</span>}
      </div>

      <div>
        <label style={labelStyle}>Role</label>
        <select {...register('role', { validate: required })} style={{ ...inputStyle, color: '#f8fafc', background: 'rgba(15, 23, 42, 0.9)' }}>
          <option value="professional" style={{ background: '#0f172a', color: '#f8fafc' }}>Professional</option>
          <option value="vendor" style={{ background: '#0f172a', color: '#f8fafc' }}>Vendor</option>
        </select>
      </div>

      <div>
        <label style={labelStyle}>Password</label>
        <input type="password" {...register('password', { validate: passwordStrength })} style={inputStyle} />
        {errors.password && <span style={{ color: '#fca5a5', fontSize: '0.8rem', display: 'block', marginTop: '0.35rem' }}>{errors.password.message}</span>}
      </div>

      <div>
        <label style={labelStyle}>Confirm Password</label>
        <input
          type="password"
          {...register('confirm_password', {
            validate: (v) => v === password || 'Passwords do not match',
          })}
          style={inputStyle}
        />
        {errors.confirm_password && <span style={{ color: '#fca5a5', fontSize: '0.8rem', display: 'block', marginTop: '0.35rem' }}>{errors.confirm_password.message}</span>}
      </div>

      <button
        type="submit"
        className="btn-primary"
        disabled={isSubmitting}
        style={{
          width: '100%',
          marginTop: '0.3rem',
          background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
          color: '#fff',
          fontWeight: 800,
          fontSize: '1rem',
          borderRadius: '0.9rem',
          padding: '0.9rem 1rem',
        }}
      >
        {isSubmitting ? 'Creating account…' : 'Create Account'}
      </button>
    </form>
  )
}
