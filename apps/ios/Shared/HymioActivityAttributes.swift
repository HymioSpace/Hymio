import ActivityKit
import Foundation

struct HymioActivityAttributes: ActivityAttributes {
  struct ContentState: Codable, Hashable {
    var title: String
    var phase: String
    var status: String
    var activeCount: Int
    var startedAt: Int
    var updatedAt: Int
    var taskID: String
  }

  var aggregateID: String
}
