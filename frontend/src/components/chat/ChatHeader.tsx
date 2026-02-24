import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

type ChatHeaderProps = {
  title?: string | undefined
  onNewChat: () => void
  canStartNewChat: boolean
}

export function ChatHeader({ title, onNewChat, canStartNewChat }: ChatHeaderProps) {
  const { isAuthenticated, signOut } = useAuth()

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b w-full bg-tv-background-secondary border-tv-border">
      <div className="flex items-center gap-3">
        {/* Stock market logo/icon */}
        <div className="w-10 h-10 rounded-lg bg-tv-accent-blue flex items-center justify-center shadow-lg">
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-tv-text-primary">
          {title || "Stock Market Data"}
        </h1>
      </div>
      <div className="flex items-center gap-3">
        <Button 
          onClick={onNewChat} 
          variant="outline" 
          className="gap-2 rounded-lg bg-tv-background-tertiary border-tv-border text-tv-text-primary hover:bg-tv-accent-blue hover:text-white transition-all duration-200" 
          disabled={!canStartNewChat}
        >
          <Plus className="h-4 w-4" />
          New Analysis
        </Button>
        {isAuthenticated && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="rounded-lg bg-tv-background-tertiary border-tv-border text-tv-text-primary hover:bg-tv-danger-red hover:text-white transition-all duration-200">
                Logout
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Confirm Logout</AlertDialogTitle>
                <AlertDialogDescription>
                  Are you sure you want to log out? You will need to sign in again to access your
                  account.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => signOut()}>Confirm</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </header>
  )
}
