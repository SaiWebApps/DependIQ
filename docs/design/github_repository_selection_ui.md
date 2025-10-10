# GitHub Repository Selection UI Design

## Overview
The repository selection interface appears after successful GitHub OAuth authentication, allowing users to browse, filter, and select repositories for dependency analysis.

## Page Layout Structure

### Header Section
```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 dependiq - Select Repository                                  │
│                                                                 │
│ Connected as: @username                        [Disconnect]     │
│ Access: 42 repositories (23 public, 19 private)                │
└─────────────────────────────────────────────────────────────────┘
```

### Search and Filter Bar
```
┌─────────────────────────────────────────────────────────────────┐
│ 🔍 [Search repositories...]                    [Filter ▼]      │
│                                                                 │
│ Quick filters:                                                  │
│ [All] [Has Dependencies] [Python] [Java/Scala] [Recently Updated] │
└─────────────────────────────────────────────────────────────────┘
```

### Repository Grid
```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐    │
│ │ 📦 my-api-proj  │ │ 📦 frontend-app │ │ 📦 data-pipeline │    │
│ │ 🐍 Python       │ │ ☕ Java         │ │ 🐍 Python       │    │
│ │ ✅ requirements │ │ ✅ pom.xml      │ │ ✅ pyproject.toml│    │
│ │ Updated 2d ago  │ │ Updated 1w ago  │ │ Updated 3d ago  │    │
│ │ [Analyze]       │ │ [Analyze]       │ │ [Analyze]       │    │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘    │
│                                                                 │
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐    │
│ │ 📦 old-project  │ │ 📦 docs-site    │ │ 📦 config-repo  │    │
│ │ ☕ Java         │ │ 📄 Markdown     │ │ 🔧 Config       │    │
│ │ ❌ No deps file │ │ ❌ No deps file │ │ ❌ No deps file │    │
│ │ Updated 6m ago  │ │ Updated 2w ago  │ │ Updated 1m ago  │    │
│ │ [Not Supported] │ │ [Not Supported] │ │ [Not Supported] │    │
│ └─────────────────┘ └─────────────────┘ └─────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Repository Card Design

Each repository card contains:

### Card Header
- **Repository name** with repository icon (📦)
- **Visibility indicator**: 🔒 (private) or 🌐 (public)
- **Star count** (if public and has stars): ⭐ 42

### Primary Language & Framework Detection
- **Language icon** and name: 🐍 Python, ☕ Java, ⚡ Scala
- **Framework hint** (if detected): "FastAPI", "Spring Boot", "Django"

### Dependency File Detection
- **Status indicator**:
  - ✅ "requirements.txt" (clickable to preview)
  - ✅ "pom.xml + 2 others" (for multi-file projects)
  - ❌ "No dependency files found"

### Repository Metadata
- **Last updated**: "Updated 2 days ago"
- **Description** (first 60 characters): "AI-powered dependency management tool..."
- **Branch selector**: "main ▼" (allows branch/tag selection)

### Action Button
- **Analyze button**: Green, prominent for supported repos
- **Not Supported**: Greyed out for repos without dependency files
- **Loading state**: Shows spinner when analysis starts

## Interactive Features

### 1. Search Functionality
```
Search covers:
- Repository name
- Description
- Language
- Detected frameworks
```

### 2. Filter Options
```
Dropdown with options:
├── Repository Type
│   ├── All repositories
│   ├── Public only
│   └── Private only
├── Language
│   ├── Python
│   ├── Java
│   ├── Scala
│   └── Other
├── Has Dependencies
│   ├── Supported projects only
│   ├── Unsupported projects only
│   └── All projects
└── Last Updated
    ├── Last week
    ├── Last month
    ├── Last 6 months
    └── All time
```

### 3. Quick Filter Pills
Pre-configured filter combinations:
- **Has Dependencies**: Shows only repos with supported dependency files
- **Python**: Shows Python projects with requirements.txt or pyproject.toml
- **Java/Scala**: Shows projects with pom.xml, build.gradle, or build.sbt
- **Recently Updated**: Shows repos updated in the last 30 days

### 4. Pagination
```
Bottom of page:
Showing 1-12 of 42 repositories    [Previous] 1 2 3 [Next]
```

## Repository Detail Modal

When user clicks on repository name, show expanded modal:

```
┌─────────────────────────────────────────────────────────────────┐
│ 📦 my-api-project                                      [✖ Close] │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                 │
│ Description: AI-powered API for dependency management and       │
│ automated code updates with intelligent compatibility checking  │
│                                                                 │
│ 🐍 Python • 🔒 Private • ⭐ 23 stars • 🍴 5 forks            │
│ Updated 2 days ago by @username                                 │
│                                                                 │
│ Dependency Files Detected:                                      │
│ ✅ requirements.txt (23 dependencies)                          │
│ ✅ pyproject.toml (build config)                               │
│                                                                 │
│ Branch/Tag Selection:                                           │
│ [main ▼] [v1.2.0] [develop] [feature/oauth]                   │
│                                                                 │
│ Project Structure Preview:                                      │
│ 📁 src/                                                        │
│ 📁 tests/                                                      │
│ 📄 requirements.txt                                            │
│ 📄 pyproject.toml                                              │
│ 📄 README.md                                                   │
│                                                                 │
│                                         [Analyze This Repo]    │
└─────────────────────────────────────────────────────────────────┘
```

## Loading and Error States

### Loading State
```
┌─────────────────────────────────────────────────────────────────┐
│ 🔄 Loading your repositories...                                │
│                                                                 │
│ [████████████████████████████████████░░░░] 85%                 │
│                                                                 │
│ Fetching repository information from GitHub...                 │
└─────────────────────────────────────────────────────────────────┘
```

### Error State
```
┌─────────────────────────────────────────────────────────────────┐
│ ❌ Unable to load repositories                                  │
│                                                                 │
│ We couldn't fetch your repositories from GitHub.               │
│ This might be due to:                                          │
│ • Network connectivity issues                                  │
│ • GitHub API rate limiting                                     │
│ • Expired authentication token                                 │
│                                                                 │
│                           [Try Again] [Reconnect to GitHub]    │
└─────────────────────────────────────────────────────────────────┘
```

### Empty State
```
┌─────────────────────────────────────────────────────────────────┐
│ 📁 No repositories found                                        │
│                                                                 │
│ We couldn't find any repositories matching your criteria.      │
│                                                                 │
│ Try:                                                            │
│ • Adjusting your search terms                                  │
│ • Changing the applied filters                                 │
│ • Creating a new repository on GitHub                          │
│                                                                 │
│                                            [Clear All Filters] │
└─────────────────────────────────────────────────────────────────┘
```

## Technical Implementation Notes

### 1. Data Loading Strategy
- **Initial load**: Fetch first 20 repositories with basic metadata
- **Dependency detection**: Async check for dependency files in background
- **Pagination**: Load additional repos on demand
- **Caching**: Cache repository data for 5 minutes to reduce API calls

### 2. Real-time Updates
- **Dependency file status**: Updates as background checks complete
- **Visual feedback**: Cards show loading spinner while checking dependency files
- **Progressive enhancement**: Core functionality works without JavaScript

### 3. Responsive Design
- **Desktop**: 3-column grid layout
- **Tablet**: 2-column grid layout
- **Mobile**: Single column with condensed card design

### 4. Accessibility
- **Keyboard navigation**: Tab through cards and filters
- **Screen reader support**: Proper ARIA labels and descriptions
- **High contrast**: Supports system dark/light mode preferences

This UI design provides a comprehensive, user-friendly interface for repository selection while maintaining consistency with your existing dependiq application design patterns.
