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
    <header className="flex items-center justify-between px-6 py-4 border-b w-full glass-effect backdrop-blur-md">
      <div className="flex items-center gap-3">
        {/* Modern logo/icon */}
        <div className="w-10 h-10 rounded-xl gradient-bg-brand flex items-center justify-center shadow-lg">
          <span className="text-white font-bold text-lg">F</span>
        </div>
        <h1 className="text-xl font-bold bg-gradient-to-r from-gray-800 to-gray-600 dark:from-gray-100 dark:to-gray-300 bg-clip-text text-transparent">
          {title || "FAST Chat"}
        </h1>
      </div>
      <div className="flex items-center gap-3">
        <Button 
          onClick={onNewChat} 
          variant="outline" 
          className="gap-2 rounded-full hover:scale-105 transition-transform duration-200 shadow-sm" 
          disabled={!canStartNewChat}
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
        {isAuthenticated && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="rounded-full hover:scale-105 transition-transform duration-200 shadow-sm">
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
