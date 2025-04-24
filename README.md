=======
# Vision Service

Vision is a set of tools for capturing and verifying human biometrics.

## Basic deployment diagram

The following is a typical deployment where Vision Service is in place. Managed by a **Controller**, which is its main consumer and the one who will start verification flows and make sure to provide the appropriate resources to get subject data.

![Basic deployment](./docs/diagrams/basic-deployment.png)

Vision Service performs biometric verification flows based on video calls and reference images. Video calls are managed by an **WebRTC server** where it will connect to retrieve subject video stream and send its own stream (which contains instructions for the subject to prove liveness). 

Once it detects that it is a live person on the other end, Vision Service gets reference images (provided by the Controller) and compares them by relying on a **Face Matcher** service.

## Biometric verification flow overview

From Vision Service point of view, the flow starts when the Controller sends a "Join Call" request: at that point, it is supposed to have already created a Video Call and invited the subject to enter to it. It will pass a `token` on this request, that will be used by the Controller to identify which flow Vision Service refers to when sends requests to the callback URLs (that the Controller will need to implement), since this is an asynchronous process.

In the middle of the flow, Vision Service will require to retrieve reference images, so once it is sure that it is a live person, it will check if it matches the one on the reference. It is responsibility of the Controller to provide, through a callback URL, the list of reference images (typically a single one, for instance, the one from user passport).

The following diagram shows an example of a typical video verification flow using Vision.

![Sample verification flow](./docs/diagrams/sample-verification-flow.png)


## API

Vision Service API is quite simple: flows are started by a simple endpoint where all configuration parameters are set, and results are posted in callback URLs that the caller must implement in order to receive updates asynchronously.

### Join Call (/join-call)

This single endpoint receives a POST with a JSON body with the following fields:

- **ws_url**: full WebSocket URL to join the call. This includes parameters like `roomId` and `peerId`
- **callback_base_url**: webhook base URL (must be implemented by the caller, see below)
- **datastore_base_url**: (OPTIONAL) Used in case reference images are stored in a Data Store (i.e. accessible in `[datastore_base_url]/r/token`)
- **token**: controller-defined string to reference the flow in callback URLs
- **lang**: user-facing ISO 639-1 language code. At the moment, only 'es' and 'en' are supported


Example: 

```curl
curl -X POST http://localhost:5000/join-call \
    -H "Content-Type: application/json" \
    -d '{
          "ws_url": "wss://dts-webrtc.dev.2060.io:443/?roomId=1234&peerId=192324",
          "datastore_base_url": "https://ds.dev.2060.io",
          "callback_base_url": "https://unic-id-issuer-dts.dev.2060.io",
          "token": "{UUID}",
          "lang": "es"
        }'
```

### Callbacks

In order to properly complete a biometric verification flow, the controller needs to implement the following callbacks:

#### Reference image list

- Type: GET
- Endpoint: [callbackBaseUrl]/list/:token


Vision Service uses this endpoint to query about input images related to a given flow (identified by the `token`). It will use them to determine if the person in the live stream is who is supposed to be.

Reference images are returned in the response body as a JSON array of strings, whose items can be either:

- A data URL containing base64-coded image (e.g. `data:image/jpeg;base64,abcd...`)
- A regular URL, accesible by Vision Service, to download through an HTTP GET (e.g. `https://myhost/myimage.jpg`)
- **Deprecated** A file ID, used in case that images are stored in a [2060 Data Store](https://github.com/2060-io/2060-datastore). To use this, `datastore_base_url` must be defined in Join Call request.

To receive feedback about the results of biometric verifications, Vision controller needs to implement two endpoints that receive PUT requests:

#### Success

- Type: PUT
- Endpoint: `[callbackBaseUrl]/success/:token`

This is called by Vision Service when a flow completes succesfully. No body data is appended.


#### Failure

- Type: PUT
- Endpoint: `[callbackBaseUrl]/failure/:token`

This is called by Vision Service when there is an error in a flow. No body data is appended.


## Installation

### Option 1: Traditional Installation

1. Clone the repository:

```terminal
git clone ...
```

2. Create a new Python environment (recommended):

```terminal
python -m venv myenv
source myenv/bin/activate # For Linux or macOS
./myenv/Scripts/activate # For Windows
```

3. Install the dependencies using pip:

```terminal
pip install -r requirements.txt
```

4. Set up the environment by creating an `.env` file with the required configuration variables.

5. Start the application:

```terminal
python main.py
```

### Option 2: Docker Installation

1. Build the Docker image from the Dockerfile:

```terminal
docker build -t vision-service .
```

2. Run the Docker container:

```terminal
docker run -d --network host vision-service
```

*Note:* As this is a WebRTC application, running the Docker container with host networking mode is recommended for better performance and compatibility.

