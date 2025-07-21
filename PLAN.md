# BrightMatter Backend API Integration Plan

## Reference Implementation
Current Boredgamer implementation: https://github.com/NewGameJay/boredgamer
- Currently uses Firebase for all data storage and event handling
- Will be migrated to use BrightMatter pipeline once stable
- Reference for Firebase auth and studio validation patterns

### Firebase Auth Pattern
- API keys stored in `studios` collection in Firestore
- Each studio has:
  - `gameId`: Unique identifier for the game
  - `apiKey`: Secret key for API authentication
  - Other studio-specific configuration
- All API requests must include:
  - `x-api-key` header for studio authentication
  - `gameId` in request body to verify game ownership

## Project Context
- Backend uses one-processor-per-entity pattern for creation events
- Each entity (leaderboard, tournament, quest) has:
  - Dedicated API endpoint
  - Dedicated Redpanda topic
  - Dedicated processor service with own consumer group
  - Specific DB schema and table
- `/events` endpoint is reserved for high-volume gameplay events
- Entity creation/management flows through dedicated processors

## Historical Progress
- ✅ Event ingestion pipeline (API → Redpanda → RDS) set up
- ✅ Event types and payload templates documented
- ✅ RDS schema for events designed
- ✅ Backend endpoints implemented (partially)
- ✅ Leaderboard processor service working
- ✅ Tournament processor fixed and working
- ✅ Quest processor implementation started
- ❌ Leaderboard endpoint still in Netlify function
- ❌ Leaderboard table missing from schema.sql

## Known Issues
- API service fails with "Group authorization failed" for `brightmatter-group`
- Quest processor has authorization issues with `quest-processor-group`
- Need to verify all processor → RDS writes

## Current Architecture

### Tournament & Quest Implementation (Target Pattern)
- ✅ API endpoints in main API service (`/src/services/api/src/index.ts`)
- ✅ Use `validateEvent` middleware for consistent validation
- ✅ Dedicated Redpanda topics (`tournament.events`, `quest.events`)
- ✅ Dedicated processor services with consumer groups
- ✅ Tables defined in `schema.sql`

### Leaderboard Implementation (Current)
- ❌ API endpoint in Netlify function (`/netlify/functions/api.ts`)
- ❌ Different validation pattern
- ✅ Dedicated Redpanda topic (`leaderboard.events`)
- ✅ Dedicated processor service
- ❌ Missing table in `schema.sql`

## Action Items

### 1. Add Redpanda ACLs
- [x] Add ACL for `brightmatter-group` (API service)
- [x] Add ACL for `quest-processor-group` (if missing)
- [x] Verify all processor groups have correct ACLs:
  - `leaderboard-processor-group` ✅
  - `quest-processor-group` ✅
  - `tournament-processor-group` ✅
  - `event-processor-group` ✅

### 2. Verify End-to-End Processing
- [✅] Start API service on port 3001
- [✅] Test leaderboard creation and processing
- [✅] Test quest creation and processing
  - Added quest schema
  - Created quest processor
  - Verified event flow
- [✅] Test tournament creation and processing
  - Added tournament schema
  - Created tournament processor
  - Verified event flow
- [✅] Verify data storage in PostgreSQL
  - Leaderboards table ✅
  - Quests table ✅
  - Quest progress table ✅
  - Tournaments table ✅
  - Tournament participants table ✅
  - Tournament history table ✅

### 3. Complete Leaderboard Migration
- [x] Add leaderboard table to schema.sql
- [ ] Move endpoint from Netlify to main API
- [ ] Update validation to use middleware

### 4. Documentation & Cleanup
- [✅] Document API endpoints
  - Added full API.md with endpoints, schemas, and validation
  - Documented all request/response formats
  - Added error handling section
- [✅] Document event types and payloads
  - Documented all event topics
  - Added event structure and types
  - Included validation rules
- [✅] Update frontend integration guide
  - Created FRONTEND_INTEGRATION.md
  - Added code examples for all endpoints
  - Included TypeScript types
  - Added best practices section
- [✅] Clean up any remaining Netlify code in main API service
  - Removed leaderboard handlers
  - Removed unused PostgreSQL code
  - Simplified routing
- [✅] Verify event flow through Redpanda
- [✅] Confirm processor writes to new table
- [✅] Remove leaderboard code from Netlify function
  - Removed leaderboard endpoints
  - Removed leaderboard types
  - Kept only game event handling
- [✅] Update API documentation

## Current Status & Issues

### API Service Issues
1. Module Resolution
   - ✅ Fixed tsconfig.json rootDir to point to ./src
   - ✅ Updated include path to src/**/*
   - ✅ API service running on port 3001

2. Firebase Auth
   - ✅ Updated auth to match Boredgamer pattern
   - ✅ Now checks studio's games array for gameId
   - ✅ Added better error logging
   - ✅ Created test studio and game in Firebase

3. Leaderboard Endpoint
   - ✅ Added leaderboard_create to valid event types
   - ✅ Successfully tested leaderboard creation
   - ✅ Event published to Redpanda topic

### Authorization
1. Redpanda ACLs
   - ✅ Added ACL for brightmatter-group
   - ✅ Added ACL for quest-processor-group
   - ✅ Verified ACLs for all processor groups

## Next Steps
1. Test tournament endpoint end-to-end
2. Test quest endpoint end-to-end
3. Remove leaderboard code from Netlify function
4. Update API documentation with new unified endpoints
5. Add integration tests for all three endpoints
6. Monitor production event processing
   - ✅ Service running on port 3001
   - ✅ Connected to Redpanda

2. End-to-End Testing
   - Test leaderboard creation
   - Test quest creation
   - Test tournament creation
   - Verify RDS storage

3. Complete Migration
   - Move leaderboard endpoint
   - Update validation
   - Remove Netlify code

4. Documentation
   - Update API docs
   - Document event flows
