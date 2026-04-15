import { useState } from 'react'
import { login as loginApi, logout as logoutApi, signup as signupApi } from '../api/authApi'

export const useAuth = () => {
  // localStorage 대신 메모리(state)에 저장 — httpOnly 쿠키가 실제 인증 담당
  const [user, setUser] = useState(null)

  const login = async (email, password) => {
    const data = await loginApi(email, password)
    setUser(data.user)
    return data
  }

  const signup = async (email, password) => {
    return await signupApi(email, password)
  }

  const logout = async () => {
    await logoutApi()
    setUser(null)
  }

  return { user, login, signup, logout }
}
