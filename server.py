import json
import csv
import logging
from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
from dateutil import parser
import math
import random
from matplotlib import cm
from matplotlib.colors import Normalize

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

current_data = None

def calculate_grid_layout(node_list, distance=300):
    grid_size = math.ceil(math.sqrt(len(node_list)))
    node_positions = {}
    for index, node in enumerate(node_list):
        row = index // grid_size
        col = index % grid_size
        node_positions[node["id"]] = {"x": col * distance, "y": row * distance, "z": 0}
    return node_positions

def calculate_circular_layout(node_list, radius=300):
    angle_increment = 2 * math.pi / len(node_list)
    node_positions = {}
    for index, node in enumerate(node_list):
        angle = index * angle_increment
        node_positions[node["id"]] = {"x": radius * math.cos(angle), "y": radius * math.sin(angle), "z": 0}
    return node_positions

def calculate_random_layout(node_list, range_x=(-10000, 10000), range_y=(-10000, 10000), range_z=(-10000, 10000)):
    node_positions = {}
    for node in node_list:
        node_positions[node["id"]] = {
            "x": random.uniform(*range_x),
            "y": random.uniform(*range_y),
            "z": random.uniform(*range_z)
        }
    return node_positions

def calculate_smart_layout(node_list, edges):
    try:
        node_positions = {}
        edge_count = {node["id"]: 0 for node in node_list}

        for edge in edges:
            edge_count[edge["source"]] += 1
            edge_count[edge["target"]] += 1

        groups = {}
        for node in node_list:
            ip = node.get('ip')
            if ip and '.' in ip:
                octets = ip.split('.')
                if len(octets) == 4:
                    third_octet = int(octets[2])
                    if third_octet not in groups:
                        groups[third_octet] = []
                    groups[third_octet].append(node)

        total_groups = len(groups)
        angle_increment = 2 * math.pi / total_groups
        radius = 4000  # Increased radius for group centers

        for index, (group, nodes) in enumerate(groups.items()):
            angle = index * angle_increment
            group_center_x = radius * math.cos(angle)
            group_center_y = radius * math.sin(angle)
            group_center_z = 0

            subgroup_radius = 600  # Increased radius for subgroups
            subgroup_angle_increment = 2 * math.pi / len(nodes)

            for sub_index, node in enumerate(nodes):
                sub_angle = sub_index * subgroup_angle_increment
                x = group_center_x + subgroup_radius * math.cos(sub_angle) + random.uniform(-300, 300)
                y = group_center_y + subgroup_radius * math.sin(sub_angle) + random.uniform(-300, 300)
                z = group_center_z + edge_count[node["id"]] * 50

                node_positions[node["id"]] = {"x": x, "y": y, "z": z}

        ungrouped_nodes = [node for node in node_list if node["id"] not in node_positions]
        ungrouped_range_x = (-5000, 5000)
        ungrouped_range_y = (-5000, 5000)
        ungrouped_range_z = (-5000, 5000)

        for node in ungrouped_nodes:
            node_positions[node["id"]] = {
                "x": random.uniform(*ungrouped_range_x),
                "y": random.uniform(*ungrouped_range_y),
                "z": random.uniform(*ungrouped_range_z)
            }

        return node_positions

    except Exception as e:
        app.logger.error(f"Error in calculate_smart_layout: {e}")
        return {}

def strip_domain(hostname):
    return hostname.split('.')[0]

def calculate_edge_color(num_edges, max_edges):
    norm = Normalize(vmin=1, vmax=max_edges)
    cmap = cm.get_cmap('jet')  # Using jet colormap for clear color transitions
    rgba = cmap(norm(num_edges))
    r, g, b, _ = [int(255 * x) for x in rgba]
    return f'rgb({r}, {g}, {b})'

def calculate_node_size(num_edges, max_edges):
    ratio = num_edges / max_edges
    size = 10 + ratio * 20
    return size

def process_csv(file, layout="grid"):
    global current_data
    nodes = {}
    edges = []
    edge_groups = {}
    ip_to_hostname = {}
    node_edge_count = {}

    try:
        file_content = file.read().decode('utf-8-sig')
        reader = list(csv.DictReader(file_content.splitlines()))

        for row in reader:
            ip_address = row.get('EventData.IpAddress', '')
            ip_resolved = row.get('IpResolved', '')

            if ip_address and ip_resolved:
                ip_to_hostname[ip_address] = strip_domain(ip_resolved)

        for row in reader:
            event_time = row.get('EventTime', '')
            computer = strip_domain(row.get('Computer', ''))
            ip_address = row.get('EventData.IpAddress', '')
            user = row.get('EventData.TargetUserName', '')

            if not event_time or not computer or not ip_address:
                continue

            time_created = parser.isoparse(event_time).timestamp()

            if ip_address in ip_to_hostname:
                source_id = ip_to_hostname[ip_address]
                source_label = f"{source_id} ({ip_address})"
                if source_id in nodes and 'ip' not in nodes[source_id]:
                    nodes[source_id]['label'] = source_label
                    nodes[source_id]['ip'] = ip_address
            else:
                source_id = ip_address
                source_label = ip_address

            if source_id not in nodes:
                nodes[source_id] = {"id": source_id, "label": source_label, "size": 10, "ip": ip_address}
            if computer not in nodes:
                nodes[computer] = {"id": computer, "label": f"{computer} ({ip_address})" if ip_address in ip_to_hostname else computer, "size": 10}

            edge = {
                "source": source_id,
                "target": computer,
                "timestamp": time_created,
                "user": user,
                "color": ''
            }

            edges.append(edge)

            edge_group_key = tuple(sorted([source_id, computer]))
            if edge_group_key not in edge_groups:
                edge_groups[edge_group_key] = []
            edge_groups[edge_group_key].append(edge)

            node_edge_count[source_id] = node_edge_count.get(source_id, 0) + 1
            node_edge_count[computer] = node_edge_count.get(computer, 0) + 1

        max_node_edges = max(node_edge_count.values(), default=1)

        for node_id, node in nodes.items():
            if 'ip' in node and node['ip'] in ip_to_hostname:
                node['color'] = 'blue'
            else:
                node['color'] = 'red'
            node['size'] = calculate_node_size(node_edge_count[node_id], max_node_edges)

        max_edges = max(len(group) for group in edge_groups.values())

        for edge_group in edge_groups.values():
            num_edges = len(edge_group)
            color = calculate_edge_color(num_edges, max_edges)
            for edge in edge_group:
                edge['color'] = color
                app.logger.debug(f"Edge from {edge['source']} to {edge['target']} colored {color}")

        node_list = list(nodes.values())

        if layout == "grid":
            node_positions = calculate_grid_layout(node_list)
        elif layout == "circular":
            node_positions = calculate_circular_layout(node_list)
        elif layout == "random":
            node_positions = calculate_random_layout(node_list)
        elif layout == "smart":
            node_positions = calculate_smart_layout(node_list, edges)
            if not node_positions:
                return {"error": "One or more nodes are missing IP addresses. All nodes must have IP addresses."}
        else:
            node_positions = calculate_random_layout(node_list)

        for node_id in nodes:
            if node_id not in node_positions:
                app.logger.error(f"Node ID {node_id} not found in calculated positions.")
                continue
            nodes[node_id].update(node_positions[node_id])

        current_data = {"nodes": node_list, "edges": edges}
    except Exception as e:
        app.logger.error(f"Error processing CSV: {e}")
        return {"error": str(e)}

    return current_data

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    layout = request.form.get('layout', 'grid')
    if not file:
        return jsonify({"error": "No file provided"}), 400

    data = process_csv(file, layout)
    if "error" in data:
        return jsonify(data), 500

    if not data.get('nodes') or not data.get('edges'):
        return jsonify({"error": "Invalid data structure"}), 500

    return jsonify(data)

@app.route('/highlight', methods=['POST'])
def highlight_data():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    data = request.get_json()
    node_id = data.get('node_id')

    if not node_id:
        return jsonify({"error": "Node ID is required"}), 400

    highlighted_edges = [edge for edge in current_data['edges'] if edge['source'] == node_id or edge['target'] == node_id]
    highlighted_nodes_ids = {node_id}
    for edge in highlighted_edges:
        highlighted_nodes_ids.add(edge['source'])
        highlighted_nodes_ids.add(edge['target'])

    highlighted_nodes = [node for node in current_data['nodes'] if node["id"] in highlighted_nodes_ids]

    highlighted_data = {
        "nodes": highlighted_nodes,
        "edges": highlighted_edges
    }

    return jsonify(highlighted_data)

@app.route('/nodes', methods=['GET'])
def get_nodes():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    node_list = [{"id": node["id"], "label": node["label"]} for node in current_data["nodes"]]
    return jsonify(node_list)

@app.route('/full_graph', methods=['GET'])
def get_full_graph():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    return jsonify(current_data)

@app.route('/filter', methods=['POST'])
def filter_data():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    try:
        data = request.get_json()
        start_date = data['start_date']
        end_date = data['end_date']

        start_timestamp = datetime.strptime(start_date, "%Y-%m-%dT%H:%M").timestamp()
        end_timestamp = (datetime.strptime(end_date, "%Y-%m-%dT%H:%M") + timedelta(days=1) - timedelta(seconds=1)).timestamp()

        filtered_edges = [
            edge for edge in current_data["edges"]
            if start_timestamp <= edge['timestamp'] <= end_timestamp
        ]

        nodes_ids = {edge["source"] for edge in filtered_edges}.union({edge["target"] for edge in filtered_edges})
        filtered_nodes = [node for node in current_data["nodes"] if node["id"] in nodes_ids]

        return jsonify({"nodes": filtered_nodes, "edges": filtered_edges})
    except Exception as e:
        app.logger.error(f"Error filtering data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/filter_by_user', methods=['POST'])
def filter_by_user_route():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    try:
        data = request.get_json()
        user = data['user']

        user_filtered_edges = [edge for edge in current_data["edges"] if user in edge["user"]]

        nodes = {edge["source"]: None for edge in user_filtered_edges}
        nodes.update({edge["target"]: None for edge in user_filtered_edges})
        user_filtered_nodes = [node for node in current_data["nodes"] if node["id"] in nodes]

        return jsonify({"nodes": user_filtered_nodes, "edges": user_filtered_edges})
    except Exception as e:
        app.logger.error(f"Error filtering by user: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/layout', methods=['POST'])
def update_layout():
    global current_data
    if current_data is None:
        return jsonify({"error": "No graph data available"}), 400

    try:
        data = request.get_json()
        layout = data.get('layout', 'grid')

        node_list = list(current_data['nodes'])

        if layout == "grid":
            node_positions = calculate_grid_layout(node_list)
        elif layout == "circular":
            node_positions = calculate_circular_layout(node_list)
        elif layout == "random":
            node_positions = calculate_random_layout(node_list)
        elif layout == "smart":
            node_positions = calculate_smart_layout(node_list, current_data['edges'])
            if not node_positions:
                return jsonify({"error": "One or more nodes are missing IP addresses. All nodes must have IP addresses."})
        else:
            node_positions = calculate_random_layout(node_list)

        for node in node_list:
            if node['id'] not in node_positions:
                app.logger.error(f"Node ID {node['id']} not found in calculated positions.")
                continue
            node.update(node_positions[node['id']])

        current_data['nodes'] = node_list
    except Exception as e:
        app.logger.error(f"Error updating layout: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify(current_data)

if __name__ == '__main__':
    app.run(debug=True)
