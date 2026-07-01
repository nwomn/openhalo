package dev.openhalo.android.edge

import java.util.concurrent.CopyOnWriteArrayList

object EdgeDiagnosticsStore {
    @Volatile
    private var currentState: EdgeDiagnostics = EdgeDiagnostics()
    private val listeners = CopyOnWriteArrayList<(EdgeDiagnostics) -> Unit>()

    fun current(): EdgeDiagnostics = currentState

    fun update(next: EdgeDiagnostics) {
        currentState = next
        listeners.forEach { listener -> listener(next) }
    }

    fun subscribe(listener: (EdgeDiagnostics) -> Unit): () -> Unit {
        listeners.add(listener)
        listener(currentState)
        return { listeners.remove(listener) }
    }
}
