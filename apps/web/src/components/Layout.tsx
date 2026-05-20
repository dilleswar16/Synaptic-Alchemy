import type { ReactNode } from 'react'
import NavBar from './NavBar'
import Footer from './Footer'

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <NavBar />
      <main
        style={{
          flex: 1,
          maxWidth: 1280,
          width: '100%',
          margin: '0 auto',
          padding: '32px 24px 48px',
        }}
      >
        {children}
      </main>
      <Footer />
    </div>
  )
}
