# Raahi — Demo Profile Dataset & Future Dating ML V3 Mapping Reference

## 1. Overview

This document specifies the structure of the 20 realistic fictional profiles created in `src/data/demoProfiles.ts` and documents the future data-mapping requirements for subsequent Dating ML V3 integration.

> **Status:** In Phase 1, ML integration is explicitly deferred. No ML models, prediction endpoints, or simulated compatibility scores are running. Raw attributes and missing/null values are strictly preserved.

---

## 2. Dataset Distribution

Total Profiles: **20**

### Completeness Breakdown

| Category | Count | Profile IDs | Characteristics |
|---|---:|---|---|
| **Complete** | 5 | 901, 906, 907, 911, 916 | 100% fields populated (age, profession, education, bio, 4+ interests, intentions, preferences) |
| **Mostly complete** | 7 | 902, 904, 905, 908, 912, 914, 918 | ~85% populated; 1 or 2 optional fields missing (e.g. education null or preferences null) |
| **Partially complete** | 5 | 903, 909, 910, 913, 917 | ~55-60% populated; 3 to 4 optional fields missing (e.g. no education, no intentions) |
| **Several missing** | 3 | 915, 919, 920 | ~25-35% populated; minimal or null bio, no education, empty or single interest, null preferences |

---

## 3. Profile Schema & ML Feature Mapping

Each profile in `TWENTY_DEMO_PROFILES` retains its raw attributes:

```typescript
export interface FictionalDemoProfile {
  id: number                           // Stable identifier (901–920)
  chatId: number                       // Stable chat thread identifier
  name: string                         // Profile display name
  age: number | null                   // Age (18–30, or null for incomplete)
  gender: 'female' | 'male' | 'non-binary' | null
  city: string                         // Geographic location
  era: GenerationId                    // 'genz' | 'zillenial' | 'millennial'
  profession: string | null            // Raw occupational text
  education: string | null             // Raw educational institution / degree
  bio: string | null                   // Natural self-written bio
  interests: string[]                  // Multi-label hobby / passion tags
  relationshipIntentions: string | null// Stated relationship goal
  preferredAgeRange: [number, number] | null // [minAge, maxAge]
  preferredDistanceKm: number | null   // Max search radius in kilometers
  preferredGenerations: GenerationId[] | null// Accepted generations
  completenessCategory: CompletenessCategory
  completenessScore: number            // Calculated completeness percentage (0–100)
  photos: string[]                     // Local bundled photo assets (3 per profile)
  initials: string
  isDemo: true                         // Guard flag to prevent mixing with real user data
  isVerified: boolean
  status: 'online' | 'offline'
  lastSeen: string
  isMatch: boolean
}
```

---

## 4. Guidelines for Future Dating ML V3 Integration

1. **Missing Value Handling:** Missing fields (`null` or empty arrays `[]`) must not be imputed with artificial dummy defaults before feature vectorization. The ML pipeline should support explicit missingness indicators (e.g. mask tokens or dedicated categorical missing levels).
2. **Text Embeddings:** `bio`, `profession`, `education`, and `interests` should be passed to semantic encoders without lossy normalization.
3. **No Faked Compatibility Scores:** In the absence of an active ML model, no random or simulated compatibility scores are to be generated or rendered.
4. **Isolated State:** Demo profile evaluations should run in a sandbox test harness without polluting real user interaction logs in production databases.
