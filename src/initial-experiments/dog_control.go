package main

import (
	"fmt"
	"os"
	"os/exec"
)

const (
	SHUTDOWN_SCRIPT = "./shutdown.sh"
	PATROL_STEPS    = 5
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: %s <command> [param]\n", os.Args[0])
		os.Exit(1)
	}
	
	command := os.Args[1]
	param := ""
	if len(os.Args) > 2 {
		param = os.Args[2]
	}
	
	dogClient := NewDogControlClient()

	// If shutdown button is pressed, shutdown the robot.
	if dogClient.IsShutdownButtonPressed() {
		cmd := exec.Command(SHUTDOWN_SCRIPT)
		err := cmd.Run()
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error running shutdown script: %v\n", err)
		}
		dogClient.Cleanup()
	}

	if dogClient.GetStep() < PATROL_STEPS {
		// Send command to the robot.
		switch command {
		case "forward":
			dogClient.MoveForward(param)
		case "backward":
			dogClient.MoveBackward(param)
		case "left":
			dogClient.TurnLeft(param)
		case "right":
			dogClient.TurnRight(param)
		case "say_hello":
			dogClient.SayHello()
		case "do_nothing":
			dogClient.DoNothing()
		default:
			fmt.Fprintf(os.Stderr, "Invalid command: %s\n", command)
			os.Exit(1)
		}

		// Get new observation
		_, description := dogClient.GetProcessedObservation()

		// Skip the image for now, only return the description of the image.
		fmt.Printf(description)
	}else{
		fmt.Fprintf(os.Stdout, "Done\n")
	}
}
