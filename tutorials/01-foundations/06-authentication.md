# Post 6: Authentication & Authorization

**Part 6 of 50** | ⏱️ 45 minutes | [← Previous](05-database-setup.md) | [Next: Environment Setup →](07-environment-setup.md)

---

## 🎯 What You'll Learn

- Supabase Auth fundamentals
- User signup and login flows
- JWT tokens and session management
- Role-based access control (RBAC)
- Protecting API endpoints

---

## 📖 Authentication vs Authorization

**Authentication:** Who are you?
- Login with email/password
- Verify identity
- Issue session token

**Authorization:** What can you do?
- Check user permissions
- Enforce access rules
- Filter data based on user

---

## 🔐 How Supabase Auth Works

### The Login Flow (Step-by-Step)

Let's trace what happens when Alice logs in:

**Step 1: Alice submits credentials**

```typescript
const { data, error } = await supabase.auth.signInWithPassword({
  email: 'alice@example.com',
  password: 'secret123'
})
```

**Step 2: Supabase validates**

```
Browser                    Supabase Auth              Database
  │                             │                         │
  ├───"alice@example.com"────▶│                         │
  │      "secret123"           │                         │
  │                             ├──"Check password"────▶│
  │                             │◀───"Valid!"─────────┤
  │◀───"Here's your token"────┤                         │
```

**Step 3: Browser receives JWT token**

A **JWT** (JSON Web Token) is like a digital ID card:

```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "user-abc-123",        // Alice's user ID
    "email": "alice@example.com",
    "role": "authenticated",
    "exp": 1737158400            // Expires in 1 hour
  },
  "signature": "..."              // Cryptographic proof
}
```

**Why a token instead of just "logged in"?**

- **Stateless**: Server doesn't need to remember "Alice is logged in"
- **Self-contained**: Token includes user ID, email, role
- **Secure**: Cryptographically signed - can't be faked
- **Expiring**: Automatically expires after 1 hour

**Step 4: Browser stores token**

Supabase automatically stores the token (in localStorage or httpOnly cookie).

**Step 5: Every request includes token**

```typescript
// When you make any API call:
const projects = await supabase
  .from('rag_projects')
  .select('*')
  .execute()

// Supabase automatically adds:
// Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Step 6: Backend validates token**

```python
# Your FastAPI endpoint
@app.get("/api/projects")
def get_projects(user = Depends(get_current_user)):
    # get_current_user:
    # 1. Extracts token from Authorization header
    # 2. Verifies signature (is it real?)
    # 3. Checks expiration (is it still valid?)
    # 4. Returns user info
    
    # Now you know WHO is making the request
    return projects_for_user(user.id)
```

### Understanding Token Expiration

**Why do tokens expire?**

Imagine your house key never expired. If stolen, the thief has **forever** to use it.

Tokens expire after 1 hour. If stolen:
- ✅ Thief only has 1 hour
- ✅ After expiration, they're locked out
- ✅ Real user gets new token automatically

**Refresh tokens: Stay logged in**

```
Access Token (1 hour)  →  Short-lived, used for requests
Refresh Token (30 days) →  Long-lived, gets new access token

Flow:
1. User logs in → Gets both tokens
2. Makes requests with access token
3. Access token expires after 1 hour
4. Supabase automatically uses refresh token to get new access token
5. User stays logged in seamlessly!
```

---

## 🚀 Frontend Auth Setup

### Create Supabase Client

```typescript
// lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)
```

### Sign Up

```typescript
'use client'

import { useState } from 'react'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export default function SignUpPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  
  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          name: email.split('@')[0],  // Default name
        }
      }
    })
    
    if (error) {
      alert(error.message)
    } else {
      alert('Check your email for confirmation link!')
    }
    
    setLoading(false)
  }
  
  return (
    <form onSubmit={handleSignUp} className="space-y-4">
      <Input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />
      
      <Input
        type="password"
        placeholder="Password (min 6 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={6}
      />
      
      <Button type="submit" disabled={loading}>
        {loading ? 'Creating account...' : 'Sign Up'}
      </Button>
    </form>
  )
}
```

### Sign In

```typescript
const handleSignIn = async (e: React.FormEvent) => {
  e.preventDefault()
  
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  })
  
  if (error) {
    alert(error.message)
  } else {
    // User is logged in!
    router.push('/chat')
  }
}
```

### Sign Out

```typescript
const handleSignOut = async () => {
  await supabase.auth.signOut()
  router.push('/login')
}
```

---

## 🎯 Session Management

### Get Current User

```typescript
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function ProfilePage() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      setLoading(false)
    })
    
    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null)
      }
    )
    
    return () => subscription.unsubscribe()
  }, [])
  
  if (loading) return <div>Loading...</div>
  
  if (!user) return <div>Please log in</div>
  
  return (
    <div>
      <h1>Welcome, {user.email}</h1>
      <p>User ID: {user.id}</p>
    </div>
  )
}
```

### Protected Route

```typescript
// components/ProtectedRoute.tsx
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.push('/login')
      } else {
        setLoading(false)
      }
    })
  }, [router])
  
  if (loading) return <div>Loading...</div>
  
  return <>{children}</>
}

// Usage in page
export default function ChatPage() {
  return (
    <ProtectedRoute>
      <ChatInterface />
    </ProtectedRoute>
  )
}
```

---

## 🔧 Backend Auth

### FastAPI with Supabase

```python
# api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Extract and validate user from JWT token.
    
    Usage:
        @app.get("/protected")
        async def protected(user = Depends(get_current_user)):
            return {"user_id": user["id"]}
    """
    token = credentials.credentials
    
    try:
        # Verify token with Supabase
        user = supabase.auth.get_user(token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        return user.user
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}"
        )
```

### Protect Endpoints

```python
from fastapi import APIRouter, Depends
from api.dependencies import get_current_user

router = APIRouter()

@router.get("/projects")
async def list_projects(user = Depends(get_current_user)):
    """List projects for current user."""
    
    # RLS automatically filters by user_id
    projects = supabase.table("rag_projects")\\
        .select("*")\\
        .eq("user_id", user["id"])\\
        .execute()
    
    return projects.data

@router.post("/projects")
async def create_project(
    request: CreateProjectRequest,
    user = Depends(get_current_user)
):
    """Create new project."""
    
    project = supabase.table("rag_projects").insert({
        "user_id": user["id"],  # Automatically use current user
        "name": request.name,
    }).execute()
    
    return project.data[0]
```

---

## 👥 Role-Based Access Control (RBAC)

### Add Roles to Users

```sql
-- Add role to user metadata
UPDATE auth.users
SET raw_user_meta_data = 
    raw_user_meta_data || '{"role": "admin"}'::jsonb
WHERE email = 'admin@example.com';
```

### Check Role in Backend

```python
from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

async def require_admin(user = Depends(get_current_user)):
    """Dependency that requires admin role."""
    role = user.get("user_metadata", {}).get("role", "user")
    
    if role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return user

@router.get("/admin/users")
async def list_all_users(admin = Depends(require_admin)):
    """Admin-only: List all users."""
    users = supabase.table("users").select("*").execute()
    return users.data
```

### Check Role in RLS

```sql
-- Admin can see all projects
CREATE POLICY "Admins can view all projects"
ON rag_projects
FOR SELECT
USING (
    (auth.jwt() -> 'user_metadata' ->> 'role') = 'admin'
);

-- Regular users see only their own
CREATE POLICY "Users can view own projects"
ON rag_projects
FOR SELECT
USING (
    auth.uid() = user_id
    AND
    COALESCE(auth.jwt() -> 'user_metadata' ->> 'role', 'user') = 'user'
);
```

---

## 💡 Real DevChat Example: Chat Endpoint

From `api/routes/chat.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.dependencies import get_current_user
from src.agents.devchat_agent import DevChatAgent

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    project_id: str

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    user = Depends(get_current_user),
    agent: DevChatAgent = Depends(get_agent)
):
    """
    Process a chat query.
    
    Requires authentication.
    Validates user has access to project.
    """
    
    # Verify user owns project (via RLS)
    project = supabase.table("rag_projects")\\
        .select("id")\\
        .eq("id", request.project_id)\\
        .eq("user_id", user["id"])\\
        .execute()
    
    if not project.data:
        raise HTTPException(
            status_code=403,
            detail="Project not found or access denied"
        )
    
    # Process query
    result = await agent.query(
        query=request.query,
        project_id=request.project_id,
        user_id=user["id"]
    )
    
    # Log usage
    supabase.table("usage_logs").insert({
        "user_id": user["id"],
        "project_id": request.project_id,
        "operation": "chat",
        "tokens_input": result["tokens"]["input"],
        "tokens_output": result["tokens"]["output"],
        "cost_usd": result["cost"]
    }).execute()
    
    return result
```

---

## 🔒 Security Best Practices

### 1. Store Tokens Securely

```typescript
// ❌ Don't store in localStorage (XSS vulnerable)
localStorage.setItem('token', token)

// ✅ Supabase handles this automatically
// Tokens stored in httpOnly cookies (if configured)
```

### 2. Use Environment Variables

```bash
# .env.local (frontend)
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJxxx  # Safe for frontend

# .env (backend)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJyyy  # NEVER expose to frontend!
```

### 3. Validate on Backend

```python
# ❌ Trust frontend data
@router.delete("/projects/{id}")
async def delete_project(id: str, user = Depends(get_current_user)):
    # User could pass any ID!
    supabase.table("rag_projects").delete().eq("id", id).execute()

# ✅ Verify ownership
@router.delete("/projects/{id}")
async def delete_project(id: str, user = Depends(get_current_user)):
    # RLS ensures user can only delete their projects
    result = supabase.table("rag_projects")\\
        .delete()\\
        .eq("id", id)\\
        .eq("user_id", user["id"])\\
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
```

---

## ✅ Knowledge Check

1. What's the difference between authentication and authorization?
2. Where is the JWT token stored in the frontend?
3. How does RLS know which user is making a request?
4. What's the difference between anon key and service key?
5. How do you protect an API endpoint with authentication?

<details>
<summary>Answers</summary>

1. Authentication = who you are, Authorization = what you can do
2. Automatically handled by Supabase (localStorage or httpOnly cookie)
3. Extracts user ID from JWT token using `auth.uid()` function
4. Anon key respects RLS (frontend), service key bypasses RLS (backend only)
5. Use `Depends(get_current_user)` dependency injection

</details>

---

**Next:** [Post 7: Environment Setup & Configuration →](07-environment-setup.md)

Learn how to set up your development environment and manage configuration.

---

[🏠 Back to Index](../README.md) | [← Previous](05-database-setup.md) | [Next: Environment Setup →](07-environment-setup.md)
