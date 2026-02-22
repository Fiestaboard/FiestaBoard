# FiestaBoard Discord Community Setup Plan

> **Purpose:** A comprehensive plan for setting up the FiestaBoard Discord server. This document is designed to be handed to an LLM with Discord MCP server access to execute the setup.

---

## Table of Contents

1. [Server Identity](#1-server-identity)
2. [Roles & Permissions](#2-roles--permissions)
3. [Onboarding & Terms of Service](#3-onboarding--terms-of-service)
4. [Channel Structure](#4-channel-structure)
5. [Rules & Moderation](#5-rules--moderation)
6. [Bot Integrations](#6-bot-integrations)
7. [Automation & Workflows](#7-automation--workflows)

---

## 1. Server Identity

| Setting | Value |
|---------|-------|
| **Server Name** | FiestaBoard |
| **Server Icon** | Use `fiesta-icon.png` from the repository |
| **Server Description** | The official FiestaBoard community — open-source split-flap display control with 18+ plugin integrations. Get help, share setups, suggest ideas, and build plugins. |
| **Default Notification Setting** | Only @mentions |
| **Verification Level** | Medium (must be registered on Discord for more than 5 minutes and a member of the server for more than 10 minutes) |
| **Explicit Media Content Filter** | Scan media content from all members |
| **Community Features** | Enable Community (required for onboarding screens, Server Discovery, and Welcome Screen) |

---

## 2. Roles & Permissions

### Role Hierarchy (top to bottom)

| Role | Color | Hoisted | Mentionable | Description |
|------|-------|---------|-------------|-------------|
| **Admin** | `#E74C3C` (Red) | Yes | No | Server owners and project leads. Full permissions. |
| **Team** | `#E67E22` (Orange) | Yes | Yes | Core maintainers and contributors with repo access. |
| **Moderator** | `#3498DB` (Blue) | Yes | Yes | Community moderators who enforce rules and manage discussions. |
| **Plugin Developer** | `#2ECC71` (Green) | Yes | Yes | Community members who develop or maintain FiestaBoard plugins. |
| **Contributor** | `#9B59B6` (Purple) | Yes | Yes | Members who have contributed code, docs, or meaningful help. |
| **Member** | `#95A5A6` (Grey) | No | No | Verified community members who accepted the ToS. |
| **@everyone** | Default | No | No | Unverified users. Can only see rules and onboarding channels. |

### Permission Matrix

| Permission | Admin | Team | Moderator | Plugin Dev | Contributor | Member | @everyone |
|------------|-------|------|-----------|------------|-------------|--------|-----------|
| Administrator | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage Server | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage Channels | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage Roles | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Manage Messages | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Kick Members | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Ban Members | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Timeout Members | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Create Invite | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Send Messages | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Embed Links | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Attach Files | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Use External Emoji | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Add Reactions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Read Message History | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Use Slash Commands | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Connect (Voice) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Speak (Voice) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| View Channels | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Limited |
| Create Public Threads | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Create Private Threads | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Mention @everyone | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Use Forum Tags | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

---

## 3. Onboarding & Terms of Service

### Community Onboarding Screen

Enable Discord's built-in **Community Onboarding** feature. When new members join, they must complete onboarding before gaining access to the server.

### Rules Screen / Terms of Service

Present the following as the **Rules Screening** that members must accept before participating:

> ### Welcome to the FiestaBoard Community! 🎉
>
> Before you can join the conversation, please read and accept our community guidelines.
>
> **By clicking "I agree" below, you confirm that you have read, understood, and agree to abide by the following terms:**
>
> #### 📜 Terms of Service
>
> 1. **Be Respectful** — Treat everyone with kindness and respect. No harassment, hate speech, discrimination, or personal attacks of any kind. We're all here because we love split-flap displays.
>
> 2. **No Spam or Self-Promotion** — Do not spam messages, links, or unsolicited promotions. Sharing your FiestaBoard setup or related projects in the appropriate channels is welcome and encouraged.
>
> 3. **Keep It On-Topic** — Use the correct channels for your messages. Off-topic conversations belong in `#off-topic`. Support questions belong in `#help` or the relevant forum.
>
> 4. **No NSFW Content** — This is an all-ages community. Do not post any explicit, violent, or otherwise inappropriate content.
>
> 5. **No Piracy or Illegal Content** — Do not share pirated software, cracks, or any content that violates intellectual property rights.
>
> 6. **Respect Privacy** — Do not share personal information about yourself or others. Do not DM other members unsolicited, especially to ask for help (use public channels instead).
>
> 7. **Follow Discord's Terms of Service** — All members must comply with [Discord's Terms of Service](https://discord.com/terms) and [Community Guidelines](https://discord.com/guidelines).
>
> 8. **Listen to Moderators** — Moderator decisions are final. If you disagree with a moderation action, you may respectfully appeal via DM to a moderator or admin.
>
> 9. **Use English** — To ensure everyone can participate, please communicate in English in all public channels.
>
> 10. **Have Fun** — This community exists to help each other get the most out of FiestaBoard. Share your setups, ask questions, suggest ideas, and enjoy!
>
> **Violations of these rules may result in warnings, timeouts, kicks, or permanent bans at moderator discretion.**

### Onboarding Flow

1. New member joins the server.
2. They are shown the **Rules Screening** (Terms of Service above).
3. They must click **"I have read and agree to the rules"** to proceed.
4. Upon acceptance, they receive the **Member** role automatically.
5. They are redirected to the **Welcome Screen** with default channels highlighted.

### Welcome Screen Configuration

| Channel | Description |
|---------|-------------|
| `#welcome` | Say hi and introduce yourself to the community! |
| `#help` | Need help setting up FiestaBoard? Start here. |
| `#showcase` | Check out what others have built with FiestaBoard. |
| `#ideas` | Have an idea for a feature or plugin? Share it here! |
| `#announcements` | Stay up to date with the latest FiestaBoard news. |

---

## 4. Channel Structure

### Category: 📢 INFO

> Public, read-only informational channels. Only Admin/Team/Moderator can post.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#announcements` | Text | Official project announcements, releases, and news | Admin, Team | Everyone (Member+) |
| `#rules` | Text | Server rules and Terms of Service (auto-generated by Community feature) | Admin | Everyone (Member+) |
| `#changelog` | Text | Auto-posted release notes and version updates | Admin, Team, Bots | Everyone (Member+) |
| `#roadmap` | Text | Current project roadmap and planned features | Admin, Team | Everyone (Member+) |

### Category: 💬 COMMUNITY

> General community interaction channels.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#welcome` | Text | New member introductions and greetings | Member+ | Everyone (Member+) |
| `#general` | Text | General FiestaBoard discussion | Member+ | Everyone (Member+) |
| `#off-topic` | Text | Non-FiestaBoard casual conversation | Member+ | Everyone (Member+) |
| `#showcase` | Text | Share photos/videos of your FiestaBoard setup | Member+ | Everyone (Member+) |
| `#memes` | Text | Lighthearted fun and memes (keep it clean) | Member+ | Everyone (Member+) |

### Category: ❓ SUPPORT

> Help and troubleshooting channels.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#help` | Forum | General help and troubleshooting (use tags for categorization) | Member+ | Everyone (Member+) |
| `#setup-guides` | Text | Curated setup guides and tutorials (read-heavy, discussion in threads) | Admin, Team, Contributor | Everyone (Member+) |
| `#faq` | Text | Frequently asked questions and answers | Admin, Team, Moderator | Everyone (Member+) |

#### `#help` Forum Tags

| Tag | Emoji | Description |
|-----|-------|-------------|
| Setup | 🔧 | Installation and initial setup issues |
| Docker | 🐳 | Docker and container-related questions |
| Plugins | 🧩 | Plugin configuration and usage |
| Display | 📟 | Physical board and display issues |
| API | ⚡ | API and Cloud API questions |
| Web UI | 🖥️ | Web interface issues |
| Raspberry Pi | 🍓 | Raspberry Pi deployment |
| Networking | 🌐 | Network, proxy, and connectivity issues |
| Resolved | ✅ | Issue has been resolved |

### Category: 🧩 PLUGINS

> Everything related to FiestaBoard plugin ecosystem.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#plugin-announcements` | Text | New plugin releases and major plugin updates | Admin, Team, Plugin Developer | Everyone (Member+) |
| `#plugin-development` | Forum | Plugin development discussion, questions, and code help | Member+ | Everyone (Member+) |
| `#plugin-requests` | Forum | Request new plugins or integrations | Member+ | Everyone (Member+) |
| `#plugin-showcase` | Text | Share your custom plugins with the community | Plugin Developer+ | Everyone (Member+) |

#### `#plugin-development` Forum Tags

| Tag | Emoji | Description |
|-----|-------|-------------|
| Help Wanted | 🆘 | Need help with plugin development |
| Code Review | 👀 | Requesting feedback on plugin code |
| Tutorial | 📚 | Plugin development tutorial or guide |
| Bug | 🐛 | Bug in an existing plugin |
| Discussion | 💬 | General plugin development discussion |
| Resolved | ✅ | Issue has been resolved |

#### `#plugin-requests` Forum Tags

| Tag | Emoji | Description |
|-----|-------|-------------|
| New Plugin | ✨ | Request for a brand new plugin |
| Enhancement | 🚀 | Enhancement to an existing plugin |
| Integration | 🔗 | Request for a third-party integration |
| Under Review | 🔍 | Request is being reviewed by the team |
| Planned | 📋 | Request has been accepted and planned |
| Completed | ✅ | Request has been fulfilled |

### Category: 💡 IDEAS & FEEDBACK

> Feature requests, ideas, and feedback.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#ideas` | Forum | Suggest new features, improvements, and ideas | Member+ | Everyone (Member+) |
| `#feedback` | Text | General feedback about FiestaBoard | Member+ | Everyone (Member+) |
| `#polls` | Text | Community polls and voting | Admin, Team, Moderator | Everyone (Member+) |

#### `#ideas` Forum Tags

| Tag | Emoji | Description |
|-----|-------|-------------|
| Feature Request | ✨ | New feature idea |
| UI/UX | 🎨 | User interface or experience improvement |
| Performance | ⚡ | Performance improvement suggestion |
| Integration | 🔗 | Third-party integration idea |
| Discussion | 💬 | Open discussion about direction |
| Under Review | 🔍 | Idea is being reviewed by the team |
| Planned | 📋 | Idea has been accepted into the roadmap |
| Implemented | ✅ | Idea has been implemented |
| Won't Do | ❌ | Idea has been declined (with explanation) |

### Category: 🤝 CONTRIBUTING

> For open-source contributors.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#contributing` | Text | Discussion about contributing to FiestaBoard | Member+ | Everyone (Member+) |
| `#good-first-issues` | Text | Curated beginner-friendly issues from GitHub | Admin, Team, Bots | Everyone (Member+) |
| `#code-review` | Text | Request or discuss code reviews | Contributor+ | Everyone (Member+) |

### Category: 🔊 VOICE

> Voice and streaming channels for the community.

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `General Voice` | Voice | General voice chat | Member+ | Everyone (Member+) |
| `Pair Programming` | Voice | Voice + screen share for pair programming / debugging | Member+ | Everyone (Member+) |
| `Community Hangout` | Stage | Stage channel for community events and AMAs | Admin, Team (speakers) | Everyone (Member+) |

### Category: 🔒 TEAM (Private)

> **Private channels visible only to Admin, Team, and Moderator roles.**

| Channel | Type | Description | Who Can Post | Who Can View |
|---------|------|-------------|--------------|--------------|
| `#team-chat` | Text | Private team discussion and coordination | Admin, Team, Moderator | Admin, Team, Moderator |
| `#team-announcements` | Text | Internal team announcements | Admin, Team | Admin, Team, Moderator |
| `#github-alerts` | Text | Automated GitHub notifications (PRs, issues, releases, CI) | Bots | Admin, Team, Moderator |
| `#github-prs` | Text | Pull request notifications and discussion | Bots, Admin, Team | Admin, Team, Moderator |
| `#github-issues` | Text | Issue notifications and triage discussion | Bots, Admin, Team | Admin, Team, Moderator |
| `#github-releases` | Text | Release and deployment notifications | Bots | Admin, Team, Moderator |
| `#moderation-log` | Text | Moderation actions log (kicks, bans, warnings) | Bots, Moderator+ | Admin, Team, Moderator |
| `#server-config` | Text | Server configuration discussion and decisions | Admin, Team | Admin, Team |
| `Team Voice` | Voice | Private voice channel for team meetings | Admin, Team, Moderator | Admin, Team, Moderator |

#### Private Category Permissions

```
🔒 TEAM category permissions:
  @everyone:       View Channels = ❌ (Deny)
  Admin:           View Channels = ✅, All permissions = ✅
  Team:            View Channels = ✅, Send Messages = ✅, Read History = ✅
  Moderator:       View Channels = ✅, Send Messages = ✅, Read History = ✅
  
#server-config channel override:
  Moderator:       View Channels = ❌ (Deny) — Admin and Team only
```

---

## 5. Rules & Moderation

### AutoMod Configuration

Enable Discord's built-in **AutoMod** with the following rules:

| Rule | Action | Configuration |
|------|--------|---------------|
| **Block Mention Spam** | Block message + timeout 5 min | Trigger: 5+ mentions in a single message |
| **Block Spam Content** | Block message + alert in `#moderation-log` | Use Discord's built-in spam heuristics |
| **Block Common Slurs** | Block message + alert in `#moderation-log` | Use Discord's default keyword list |
| **Block Invite Links** | Block message + alert in `#moderation-log` | Block Discord invite links in all channels except `#off-topic` |
| **Block Excessive Caps** | Flag for review | Messages with 70%+ caps and 10+ characters |
| **New Account Gate** | Flag for review | Accounts less than 7 days old (supplements server-level verification; catches alt/ban-evasion accounts) |

### Moderation Escalation Ladder

| Offense Level | Action | Duration | Example |
|---------------|--------|----------|---------|
| **1st offense (minor)** | Verbal warning via DM | — | Off-topic message in wrong channel |
| **2nd offense** | Written warning + message deletion | — | Repeated off-topic behavior |
| **3rd offense** | Timeout | 1 hour | Continued rule violations |
| **4th offense** | Timeout | 24 hours | Pattern of disruptive behavior |
| **5th offense** | Kick | — | Refusing to follow rules |
| **Severe offense** | Permanent ban | Permanent | Hate speech, doxxing, NSFW, or illegal content |

### Slow Mode Defaults

| Channel | Slow Mode |
|---------|-----------|
| `#general` | 5 seconds |
| `#off-topic` | 5 seconds |
| `#help` (forum) | None |
| `#showcase` | 30 seconds |
| All other channels | None |

---

## 6. Bot Integrations

### Required Bots

| Bot | Purpose | Key Channels |
|-----|---------|--------------|
| **GitHub Bot** (official Discord GitHub integration or webhook) | Post GitHub activity to team channels | `#github-alerts`, `#github-prs`, `#github-issues`, `#github-releases`, `#changelog`, `#good-first-issues` |
| **MEE6** or **Carl-bot** | Auto-moderation, welcome messages, reaction roles | Server-wide |

### GitHub Integration Setup

Configure GitHub webhooks or the official GitHub Discord integration for the `Fiestaboard/FiestaBoard` repository:

#### Public Channels (via bot formatting)

| GitHub Event | Discord Channel | Format |
|--------------|-----------------|--------|
| New Release Published | `#changelog` | Embed with version, release notes, and download links |
| Issues labeled `good first issue` | `#good-first-issues` | Embed with issue title, description, and link |

#### Private Team Channels (full notifications)

| GitHub Event | Discord Channel |
|--------------|-----------------|
| All push events | `#github-alerts` |
| Pull request opened/closed/merged | `#github-prs` |
| Issue opened/closed/commented | `#github-issues` |
| Release published | `#github-releases` |
| CI/CD workflow failures | `#github-alerts` |
| Dependabot alerts | `#github-alerts` |
| Security advisories | `#github-alerts` |

### Welcome Bot Configuration

When a new member completes onboarding (accepts rules), the bot should post in `#welcome`:

```
🎉 Welcome to FiestaBoard, {user}!

Here are some places to get started:
• 📢 #announcements — Stay up to date
• ❓ #help — Get help with your setup
• 🧩 #plugin-development — Build something cool
• 💡 #ideas — Share your ideas
• 📸 #showcase — Show off your board!

Check out our docs at https://fiestaboard.github.io
```

---

## 7. Automation & Workflows

### Thread Auto-Creation

| Channel | Behavior |
|---------|----------|
| `#showcase` | Encourage members to post in threads (pin a message explaining this) |
| `#feedback` | Encourage members to post in threads for each topic |

### Forum Post Defaults

| Forum Channel | Default Sort | Require Tag | Auto-Archive |
|---------------|-------------|-------------|--------------|
| `#help` | Recent Activity | Yes | 3 days of inactivity |
| `#plugin-development` | Recent Activity | Yes | 7 days of inactivity |
| `#plugin-requests` | Recent Activity | Yes | 7 days of inactivity |
| `#ideas` | Recent Activity | Yes | 7 days of inactivity |

### Periodic Tasks

| Task | Frequency | Owner |
|------|-----------|-------|
| Review and archive stale forum posts | Weekly | Moderator |
| Update `#roadmap` with current plans | Monthly | Admin/Team |
| Review and update `#faq` | Monthly | Moderator |
| Audit role assignments | Quarterly | Admin |
| Review and refresh AutoMod rules | Quarterly | Admin |

### Role Assignment Automation

| Trigger | Action |
|---------|--------|
| Member accepts Rules Screening | Grant **Member** role |
| PR merged to FiestaBoard repo | Eligible for **Contributor** role (manual grant by Team) |
| Published a community plugin | Eligible for **Plugin Developer** role (request in `#contributing`) |

---

## Implementation Checklist

Use this checklist when executing the setup via Discord MCP server:

- [ ] Create the server with name, icon, and description
- [ ] Enable Community features and set verification level
- [ ] Create all roles in hierarchy order (Admin → Team → Moderator → Plugin Developer → Contributor → Member)
- [ ] Configure role permissions as specified in the permission matrix
- [ ] Set up Rules Screening with the Terms of Service text
- [ ] Configure the Welcome Screen with highlighted channels
- [ ] Create **📢 INFO** category and its channels
- [ ] Create **💬 COMMUNITY** category and its channels
- [ ] Create **❓ SUPPORT** category and its channels (including forum setup with tags)
- [ ] Create **🧩 PLUGINS** category and its channels (including forum setup with tags)
- [ ] Create **💡 IDEAS & FEEDBACK** category and its channels (including forum setup with tags)
- [ ] Create **🤝 CONTRIBUTING** category and its channels
- [ ] Create **🔊 VOICE** category and its channels
- [ ] Create **🔒 TEAM** private category and its channels with permission overrides
- [ ] Configure AutoMod rules
- [ ] Set slow mode on specified channels
- [ ] Set up GitHub webhooks/integration for public and private channels
- [ ] Configure welcome bot messages
- [ ] Set forum channel defaults (sort, required tags, auto-archive)
- [ ] Pin introductory messages in key channels
- [ ] Test the full onboarding flow with a test account
- [ ] Invite initial team members and assign Admin/Team roles
