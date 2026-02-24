/**
 * Message History Utility
 * 
 * Manages conversation history in localStorage for quick access to recent prompts.
 * Stores the last 10 user messages for reuse.
 */

const HISTORY_KEY = 'stockMarketData_messageHistory';
const MAX_HISTORY_SIZE = 10;

export interface MessageHistoryItem {
  text: string;
  timestamp: number;
}

/**
 * Get message history from localStorage
 * 
 * @returns Array of message history items, newest first
 */
export function getMessageHistory(): MessageHistoryItem[] {
  try {
    const stored = localStorage.getItem(HISTORY_KEY);
    if (!stored) return [];
    
    const history = JSON.parse(stored) as MessageHistoryItem[];
    return Array.isArray(history) ? history : [];
  } catch (error) {
    console.error('Failed to load message history:', error);
    return [];
  }
}

/**
 * Add a message to history
 * Maintains FIFO queue of max 10 messages
 * 
 * @param message - The message text to add
 */
export function addMessageToHistory(message: string): void {
  if (!message.trim()) return;
  
  try {
    const history = getMessageHistory();
    
    // Don't add duplicates of the most recent message
    if (history.length > 0 && history[0].text === message.trim()) {
      return;
    }
    
    // Add new message at the beginning
    const newItem: MessageHistoryItem = {
      text: message.trim(),
      timestamp: Date.now(),
    };
    
    // Keep only the last MAX_HISTORY_SIZE messages
    const updatedHistory = [newItem, ...history].slice(0, MAX_HISTORY_SIZE);
    
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updatedHistory));
  } catch (error) {
    console.error('Failed to save message to history:', error);
  }
}

/**
 * Clear all message history
 */
export function clearMessageHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch (error) {
    console.error('Failed to clear message history:', error);
  }
}

/**
 * Get recent messages as simple string array
 * 
 * @param limit - Maximum number of messages to return (default: 10)
 * @returns Array of message strings
 */
export function getRecentMessages(limit: number = MAX_HISTORY_SIZE): string[] {
  const history = getMessageHistory();
  return history.slice(0, limit).map(item => item.text);
}
