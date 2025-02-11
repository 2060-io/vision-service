=======
# Vision Service

## Description

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

## Usage

1. Access the application by opening a web browser and navigating to the specified URL.

2. Follow the on-screen instructions to establish a WebRTC connection and start video streaming.

