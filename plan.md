### Detailed Plan for Avatar App Enhancements

We will break the plan into very specific tasks and follow a step-by-step approach for each goal, ensuring that all aspects (avatar selection, voice sentiment analysis, emotion tracking, etc.) are implemented efficiently.

#### 1. **Simplify User Interaction and Add Male/Female Avatar Option**

**Goal**: Make the app simpler, with an immediate option for users to choose between male and female avatars, and remove unnecessary setup options.

##### Actions:
- **Avatar Selection**:
  - Offer only two avatars (male and female) to the user on the landing page. 
  - Remove complex features like choosing avatar IDs, languages, or knowledge IDs. This will make the app easier to use, especially for elderly users.
- **Navigation**:
  - In the `navbar.tsx`, remove external links to SDKs, API Docs, and other pages irrelevant to the user. Only show options for **"Start Conversation"** and **"Logout"** (if a user authentication flow exists).
- **Immediate Avatar Load**:
  - Once an avatar (male or female) is selected, the conversation should begin immediately. The app should directly go to the speaking mode without requiring the user to click "Start" or choose further options.

##### Testing:
- Run the app and verify that only the essential buttons and avatar choices are visible.
- Ensure that when a user selects an avatar, the app immediately moves to conversation mode without requiring extra clicks.

##### **Granular Steps**:
- Update `navbar.tsx` to remove unnecessary links.
- In `InteractiveAvatar.tsx`, create a simple landing page that lets users select between a male or female avatar.
- After selection, the avatar session starts immediately.

---

#### 2. **Integrate Hume API for Emotion Detection**

**Goal**: Measure user emotions through voice sentiment analysis, store the audio and emotion data with timestamps, and display insights in the UI.

##### Actions:
- **API Route Setup**:
  - Create a new API route at `pages/api/audio-analysis.ts` that receives audio data from the front end and sends it to Hume's API for analysis. This route will also return sentiment/emotion information.
- **Sending Audio to Hume**:
  - In `InteractiveAvatar.tsx`, after every user interaction (e.g., after the avatar speaks or after the user speaks), send the audio to the Hume API. This API call will analyze the emotional state of the user.
- **Store Timestamps**:
  - Capture timestamps for each audio segment sent to Hume. Use the JavaScript `Date.now()` function or a similar method to record the exact time the user interacted with the avatar and their emotional state.
- **Display Emotional Insights**:
  - Display the emotional response data (e.g., happiness, sadness, calmness) on the screen in a simple text or chart format (using a library like Chart.js).

##### Research Required:
- **Hume API Limits**:
  - Check how much audio the Hume API can analyze at a time. Typically, APIs have a limit on how many seconds of audio you can send in a single request.
  - Understand the response format of the Hume API so you can parse it and display it correctly.
  
##### **Granular Steps**:
1. **Set up API Route**:
   - Create a file at `pages/api/audio-analysis.ts` that will:
     1. Receive the audio data from the client.
     2. Forward it to Hume’s API for analysis.
     3. Return the emotion analysis back to the client.
2. **Send Audio Data**:
   - In `InteractiveAvatar.tsx`, after every interaction, collect and send the audio data to this new API route.
3. **Display Emotion Data**:
   - Parse the emotion response and display it in a user-friendly format (e.g., “User is feeling happy” or display it as a chart).

##### Testing:
- Test if the app successfully sends audio to Hume API after each interaction.
- Test if emotion data is returned and displayed correctly.
- Make sure to test with different emotions to validate the accuracy of the results.

---

#### 3. **Store User Data in ChromaDB and SQLite**

**Goal**: Store user interactions, emotions, and therapeutic history using ChromaDB for vector data and SQLite for structured data.

##### Actions:
- **Vector DB (ChromaDB)**:
  - ChromaDB will be used to store conversation embeddings (numerical representations of conversation text). For each interaction (after the conversation ends), convert the text into embeddings using a transformer model (such as OpenAI's `text-embedding-ada`).
  - Store these embeddings in ChromaDB for future retrieval (e.g., for analyzing long-term therapy progress).
  - Create a new API route in `pages/api/store-vectors.ts` to handle this storage process.
  
- **Structured Data (SQLite)**:
  - SQLite will store the structured data, such as user profiles (name, age, health conditions) and the timestamped emotion data (from the Hume API). This will create a long-term record of each session.
  - Set up SQLite using `better-sqlite3` or another SQLite library for Node.js.
  - Store each user’s session history, including timestamps, emotions, and conversation data.

##### **Granular Steps**:
1. **Set Up ChromaDB**:
   - Set up a ChromaDB instance for vector storage.
   - Create a backend route (`pages/api/store-vectors.ts`) that:
     1. Converts conversation text to embeddings.
     2. Stores these embeddings in ChromaDB.
   
2. **Set Up SQLite**:
   - Install SQLite and set up a table schema to store user information (name, age, emotional data, session timestamps).
   - Create API routes (e.g., `pages/api/store-session.ts`) to store user session data after every conversation.

##### Testing:
- Verify that conversations are being stored as vectors in ChromaDB.
- Verify that structured data (e.g., user info and session history) is stored correctly in SQLite.
- Test retrieval of data from both databases to ensure consistency.

---

### Summary of Key Changes

1. **Simplify User Interaction**:
   - Remove unnecessary setup steps and external links.
   - Display only two avatars (male and female) for the user to choose from.

2. **Integrate Hume API**:
   - Set up API routes to send audio data to Hume.
   - Display emotion results and track timestamps for each interaction.

3. **Data Storage (ChromaDB and SQLite)**:
   - Store conversation embeddings in ChromaDB and user information/emotion data in SQLite.
   - Build a long-term therapeutic record for each user.

Once this plan is executed step by step, you will have a functional avatar app tailored for elderly adults, with integrated emotion tracking and data storage. Would you like to start with simplifying the user interface first, or move directly into integrating Hume API for sentiment detection?
