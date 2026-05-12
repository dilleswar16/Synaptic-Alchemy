import type { ReactNode } from 'react'
import NavBar from './NavBar'
import Footer from './Footer'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <NavBar />
      <main
        style={{
          flex: 1,
          maxWidth: 1280,
          width: '100%',
          margin: '0 auto',
          padding: '28px 24px 40px',
        }}
      >
        {children}
      </main>
      <Footer />
    </div>
  )
}
