package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net"
	"time"

	pb "github.com/kedacore/keda/v2/pkg/scalers/externalscaler"
	"google.golang.org/grpc"
)

type PAction struct {
	Action int64 `json:"action"`
}

type ExternalScaler struct {
	pb.UnimplementedExternalScalerServer
}

// Fetch data from the service and convert to int64
func getData() (int64, error) {
	filename := "/tmp/shared_file.json"
	var data PAction
	
	rep, err := ioutil.ReadFile(filename)
	if err != nil {
		
		return 0, fmt.Errorf("could not read file: %v", err)
	}

	err = json.Unmarshal(rep, &data)
	if err != nil {
		return 0, fmt.Errorf("could not unmarshal JSON: %v", err)
	}

	return data.Action, nil

}

// Check if the scaler is active
func (e *ExternalScaler) IsActive(ctx context.Context, ScaledObject *pb.ScaledObjectRef) (*pb.IsActiveResponse, error) {
	value, err := getData()
	if err != nil {
		fmt.Println("Error getting value:", err)
		return nil, err
	}

	return &pb.IsActiveResponse{
		Result: value >= 0,
	}, nil
}

// StreamIsActive is not implemented
func (e *ExternalScaler) StreamIsActive(ref *pb.ScaledObjectRef, stream pb.ExternalScaler_StreamIsActiveServer) error {
	for {
		select {
		case <-stream.Context().Done():
			return nil
		case <-time.After(100 * time.Millisecond):
			value, err := getData()
			if err != nil {
				fmt.Println("Error getting value:", err)
				return err
			}		
				

			
				err = stream.Send(&pb.IsActiveResponse{
					Result: value>0,
				})
				if err != nil {
					fmt.Println("Error sending stream response:", err)
					return err
				}
			
		}
	}
}

// GetMetricSpec provides the metric specification
func (e *ExternalScaler) GetMetricSpec(ctx context.Context, ref *pb.ScaledObjectRef) (*pb.GetMetricSpecResponse, error) {
	return &pb.GetMetricSpecResponse{
		MetricSpecs: []*pb.MetricSpec{{
			MetricName: "constant_metric",
			TargetSize: 1,
		}},
	}, nil
}

// GetMetrics provides the current metric values
func (e *ExternalScaler) GetMetrics(ctx context.Context, req *pb.GetMetricsRequest) (*pb.GetMetricsResponse, error) {
	desired, err := getData()
	if err != nil {
		err = fmt.Errorf("Error getting desired value: %w", err)
		fmt.Println(err)
		return nil, err
	}
	log.Printf("Returning metric value: %d (desired pods: %d)",desired*100,desired)
	return &pb.GetMetricsResponse{
		MetricValues: []*pb.MetricValue{{
			MetricName:  "constant_metric",
			MetricValue: desired,
		}},
	}, nil
}

func main() {
	grpcAddress := "0.0.0.0:50051"
	listener, err := net.Listen("tcp", grpcAddress)
	if err != nil {
		log.Fatalf("failed to listen: %v\n", err)
	}

	grpcServer := grpc.NewServer()
	pb.RegisterExternalScalerServer(grpcServer, &ExternalScaler{})
	fmt.Printf("Server listening on %s\n", grpcAddress)
	if err := grpcServer.Serve(listener); err != nil {
		log.Fatalf("failed to serve: %v\n", err)
	}
}
